"""RunService: run lifecycle, event bus and persistence (Service Layer)."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from api.result_mapper import get_result_mapper
from api.runners import EXP_NAME, PipelineRunner, RunSpec, SubprocessPipelineRunner, progress_event, utc_now
from api.schemas import RunCreate

TERMINAL = {"completed", "failed", "cancelled"}
MAX_LOGS = 4000


class RunRecord:
    def __init__(self, spec: RunSpec, ui_mode: str):
        self.spec = spec
        self.ui_mode = ui_mode
        self.status = "queued"
        self.created_at = utc_now()
        self.finished_at: Optional[str] = None
        self.current_stage: Optional[str] = None
        self.error: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.exit_code: Optional[int] = None
        self.events: List[Dict[str, Any]] = []
        self.logs: List[Dict[str, Any]] = []
        self.subscribers: List["queue.Queue[Dict[str, Any]]"] = []
        self.lock = threading.Lock()
        self.cancel = threading.Event()

    # ── event bus ────────────────────────────────────────────────────
    def publish(self, event: Dict[str, Any]) -> None:
        with self.lock:
            self.events.append(event)
            for q in self.subscribers:
                q.put(event)

    def subscribe(self):
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        with self.lock:
            snapshot = list(self.events)
            self.subscribers.append(q)
        return snapshot, q

    def unsubscribe(self, q) -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    # ── views ────────────────────────────────────────────────────────
    def summary(self, include_result: bool = False) -> Dict[str, Any]:
        data = {
            "run_id": self.spec.run_id, "name": self.spec.name, "target": self.spec.target,
            "mode": self.ui_mode, "cli_mode": self.spec.cli_mode, "status": self.status,
            "created_at": self.created_at, "finished_at": self.finished_at,
            "current_stage": self.current_stage, "error": self.error,
            "workspace": str(self.spec.workspace), "exit_code": self.exit_code,
            "max_iterations": self.spec.max_iters, "attack_rounds": self.spec.attack_rounds,
        }
        if include_result:
            data["result"] = self.result
        return data

    def persist(self) -> None:
        try:
            self.spec.workspace.mkdir(parents=True, exist_ok=True)
            payload = self.summary(include_result=True)
            payload["requirement"] = self.spec.requirement
            (self.spec.workspace / "run.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError:
            pass


class RunService:
    def __init__(self, project_root: Path, runner: Optional[PipelineRunner] = None,
                 max_parallel: Optional[int] = None, load_persisted: bool = True):
        self.project_root = Path(project_root).resolve()
        self.experiments_dir = self.project_root / "experiments" / EXP_NAME
        self.runner = runner or SubprocessPipelineRunner(self.project_root)
        self._runs: Dict[str, RunRecord] = {}
        self._lock = threading.Lock()
        slots = max_parallel or int(os.getenv("LEVER_API_MAX_PARALLEL_RUNS", "1"))
        self._slots = threading.Semaphore(max(1, slots))
        if load_persisted:
            self._load_persisted()

    # ── persistence ──────────────────────────────────────────────────
    def _load_persisted(self) -> None:
        if not self.experiments_dir.is_dir():
            return
        for path in sorted(self.experiments_dir.glob("*/run.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            spec = RunSpec(
                run_id=data.get("run_id", path.parent.name), name=data.get("name", ""),
                requirement=data.get("requirement", ""), target=data.get("target", "solidity"),
                cli_mode=data.get("cli_mode", "full"), max_iters=int(data.get("max_iterations", 3)),
                attack_rounds=int(data.get("attack_rounds", 3)), workspace=path.parent,
            )
            record = RunRecord(spec, data.get("mode", "full"))
            record.created_at = data.get("created_at", record.created_at)
            record.finished_at = data.get("finished_at")
            record.exit_code = data.get("exit_code")
            record.result = data.get("result")
            record.error = data.get("error")
            record.status = data.get("status", "failed")
            if record.status not in TERMINAL:
                record.status = "failed"
                record.error = "The API server restarted while this run was in progress."
                record.publish({"type": "error", "message": record.error})
            elif record.result is not None:
                record.events.append({"type": "result", "result": record.result})
            elif record.error:
                record.events.append({"type": "error", "message": record.error})
            self._runs[spec.run_id] = record

    # ── queries ──────────────────────────────────────────────────────
    def get(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    def list(self) -> List[RunRecord]:
        return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)

    @property
    def active_count(self) -> int:
        return sum(1 for r in self._runs.values() if r.status in {"queued", "running"})

    # ── lifecycle ────────────────────────────────────────────────────
    def create(self, payload: RunCreate, model: Optional[str] = None) -> RunRecord:
        from core.adapter_factory import adapter_factory  # Factory: validates/route target
        adapter_factory(payload.target)  # raises ValueError for unknown targets

        run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        spec = RunSpec(
            run_id=run_id, name=payload.name or "Untitled build", requirement=payload.requirement,
            target=payload.target, cli_mode=payload.cli_mode, max_iters=payload.max_iterations,
            attack_rounds=payload.attack_rounds, workspace=self.experiments_dir / run_id,
            model=model or os.getenv("LLM_MODEL") or None,
        )
        record = RunRecord(spec, payload.mode)
        with self._lock:
            self._runs[run_id] = record
        record.persist()
        threading.Thread(target=self._execute, args=(record,), name=f"lever-run-{run_id}", daemon=True).start()
        return record

    def cancel(self, run_id: str) -> Optional[RunRecord]:
        record = self.get(run_id)
        if record is None:
            return None
        if record.status in {"queued", "running"}:
            record.cancel.set()
        return record

    def _execute(self, record: RunRecord) -> None:
        spec = record.spec
        record.publish(progress_event(stage="Queued", message="Run queued; waiting for a pipeline slot."))
        with self._slots:
            if record.cancel.is_set():
                self._finish(record, "cancelled", "Run cancelled before it started.")
                return
            record.status = "running"
            record.publish(progress_event(
                stage="Starting",
                message=f"Starting {spec.target} pipeline (mode {spec.cli_mode}, max {spec.max_iters} iterations) in {spec.workspace}"))

            def emit(event: Dict[str, Any]) -> None:
                if event.get("type") == "progress":
                    if event.get("stage"):
                        record.current_stage = event["stage"]
                    if event.get("log"):
                        record.logs.append(event["log"])
                        if len(record.logs) > MAX_LOGS:
                            del record.logs[: len(record.logs) - MAX_LOGS]
                record.publish(event)

            try:
                exit_code = self.runner.run(spec, emit, record.cancel)
            except Exception as exc:  # launcher failure, not a pipeline verdict
                self._finish(record, "failed", f"Could not launch the pipeline: {exc}")
                return
            record.exit_code = exit_code

            if record.cancel.is_set():
                self._finish(record, "cancelled", "Run cancelled by the user. Backend processes were stopped.")
                return

            try:
                result = get_result_mapper(spec.target).map(spec, exit_code, record.logs)
            except Exception as exc:
                self._finish(record, "failed", f"Pipeline finished (exit {exit_code}) but its output could not be read: {exc}")
                return
            if result is None:
                tail = next((l["message"] for l in reversed(record.logs)
                             if l["message"].startswith(("PIPELINE EXECUTION ERROR", "LLM EXECUTION ERROR", "LLM Error"))), None)
                self._finish(record, "failed", tail or f"The pipeline exited with code {exit_code} without producing source code.")
                return

            record.result = result
            record.finished_at = utc_now()
            record.publish({"type": "result", "result": result})
            record.status = "completed"
            record.persist()

    def _finish(self, record: RunRecord, status: str, error: Optional[str]) -> None:
        record.error = error
        record.finished_at = utc_now()
        if error:
            record.publish({"type": "error", "message": error})
        record.status = status
        record.persist()

    # ── NDJSON streaming ─────────────────────────────────────────────
    def stream(self, run_id: str, heartbeat_s: float = 15.0) -> Iterator[str]:
        record = self.get(run_id)
        if record is None:
            yield json.dumps({"type": "error", "message": f"Unknown run '{run_id}'."}) + "\n"
            return
        snapshot, q = record.subscribe()
        try:
            for event in snapshot:
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
                if event.get("type") in {"result", "error"}:
                    return
            while True:
                terminal = record.status in TERMINAL
                try:
                    event = q.get(timeout=0.05 if terminal else heartbeat_s)
                except queue.Empty:
                    if terminal:
                        return
                    yield json.dumps({"type": "heartbeat", "ts": utc_now()}) + "\n"
                    continue
                yield json.dumps(event, ensure_ascii=False, default=str) + "\n"
                if event.get("type") in {"result", "error"}:
                    return
        finally:
            record.unsubscribe(q)
