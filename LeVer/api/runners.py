"""Pipeline runner strategies.

``SubprocessPipelineRunner`` launches ``python -m core.main_pipeline`` for a
run and converts its stdout into NDJSON progress events. A subprocess (rather
than an in-process call) is used because the engine's ``GLOBAL_LOGGER`` and
``os.environ`` mutations are process-wide, and it makes cancellation a clean
process kill.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Pattern, Tuple

EXP_NAME = "api"

EmitFn = Callable[[Dict], None]


@dataclass
class RunSpec:
    run_id: str
    name: str
    requirement: str
    target: str
    cli_mode: str
    max_iters: int
    attack_rounds: int
    workspace: Path
    model: Optional[str] = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def progress_event(stage: Optional[str] = None, message: Optional[str] = None,
                   level: str = "info") -> Dict:
    event: Dict = {"type": "progress"}
    if stage:
        event["stage"] = stage
    if message is not None:
        event["log"] = {"level": level, "message": message, "timestamp": utc_now()}
    return event


# ── Stage detection ──────────────────────────────────────────────────
# Maps lines printed by the existing pipeline (unchanged) to UI stages.
# Frontend stage names: Generate, Compile, Formal checks, Dynamic tests, Report.

_StageRule = Tuple[Pattern[str], Callable[[re.Match], str]]

COMMON_RULES: List[_StageRule] = [
    (re.compile(r"^=+ ITERATION (\d+)/(\d+)"), lambda m: f"Iteration {m.group(1)}/{m.group(2)}"),
    (re.compile(r"^PIPELINE (PASSED|FAILED|GENERATED)"), lambda m: "Report"),
]

SOLIDITY_RULES: List[_StageRule] = COMMON_RULES + [
    (re.compile(r"^1\. Generating Solidity"), lambda m: "Generate"),
    (re.compile(r"^1\. Repairing"), lambda m: "Generate (repair)"),
    (re.compile(r"^2\. Compiling"), lambda m: "Compile"),
    (re.compile(r"^Selecting Verification Properties"), lambda m: "Property selection"),
    (re.compile(r"^Architecting Lean 4 Model"), lambda m: "Formal checks"),
    (re.compile(r"^Identified \d+ theorems"), lambda m: "Formal checks (proofs)"),
    (re.compile(r"^Building Simulation Environment"), lambda m: "Dynamic tests"),
    (re.compile(r"^\s+Running Slither"), lambda m: "Static analysis"),
    (re.compile(r"^\s+Running LLM audit"), lambda m: "LLM audit"),
]

SOLANA_RULES: List[_StageRule] = COMMON_RULES + [
    (re.compile(r"^1\. Generating Anchor"), lambda m: "Generate"),
    (re.compile(r"^1\. Repairing"), lambda m: "Generate (repair)"),
    (re.compile(r"^2\. Validating Anchor"), lambda m: "Validate"),
    (re.compile(r"^3\. Anchor build"), lambda m: "Report"),
]

STAGE_RULES: Dict[str, List[_StageRule]] = {"solidity": SOLIDITY_RULES, "solana": SOLANA_RULES}

_ERROR_HINTS = re.compile(r"FAILED|ERROR|Error:|Traceback|Exception", re.IGNORECASE)
_WARN_HINTS = re.compile(r"SKIPPING|skipped|Warning|unavailable|not implemented|Retrying", re.IGNORECASE)


class StageParser:
    def __init__(self, target: str):
        self.rules = STAGE_RULES.get(target, COMMON_RULES)

    def stage_for(self, line: str) -> Optional[str]:
        for pattern, render in self.rules:
            match = pattern.search(line)
            if match:
                return render(match)
        return None

    @staticmethod
    def level_for(line: str) -> str:
        if _ERROR_HINTS.search(line):
            return "error"
        if _WARN_HINTS.search(line):
            return "warning"
        return "info"


# ── Runner strategy ──────────────────────────────────────────────────

class PipelineRunner(ABC):
    @abstractmethod
    def run(self, spec: RunSpec, emit: EmitFn, cancel: threading.Event) -> int:
        """Execute the pipeline, emitting NDJSON-shaped events. Return exit code."""


class SubprocessPipelineRunner(PipelineRunner):
    def __init__(self, project_root: Path, python: Optional[str] = None):
        self.project_root = Path(project_root)
        self.python = python or sys.executable

    def build_command(self, spec: RunSpec, req_file: Path) -> List[str]:
        cmd = [
            self.python, "-m", "core.main_pipeline",
            "--target", spec.target,
            "--mode", spec.cli_mode,
            "--req-file", str(req_file),
            "--exp-name", EXP_NAME,
            "--run-id", spec.run_id,
            "--max-iters", str(spec.max_iters),
            "--attack-rounds", str(spec.attack_rounds),
        ]
        if spec.model:
            cmd += ["--model", spec.model]
        return cmd

    def run(self, spec: RunSpec, emit: EmitFn, cancel: threading.Event) -> int:
        spec.workspace.mkdir(parents=True, exist_ok=True)
        req_file = spec.workspace / "requirement.txt"
        req_file.write_text(spec.requirement, encoding="utf-8")

        env = dict(os.environ)
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
        cmd = self.build_command(spec, req_file)
        emit(progress_event(message=f"$ {' '.join(cmd[1:])}"))

        proc = subprocess.Popen(
            cmd, cwd=str(self.project_root), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        parser = StageParser(spec.target)

        def watch_cancel():
            # Poll so the watcher exits with the process instead of leaking a thread.
            while proc.poll() is None:
                if cancel.wait(0.5):
                    if proc.poll() is None:
                        proc.kill()
                    return

        threading.Thread(target=watch_cancel, name=f"cancel-{spec.run_id}", daemon=True).start()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                if not line.strip():
                    continue
                emit(progress_event(stage=parser.stage_for(line), message=line,
                                    level=parser.level_for(line)))
            return proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
