"""Map a finished run workspace to the frontend ``GenerationResult``.

One mapper per target (Strategy). Mappers only read artifacts the existing
pipeline already writes (``Target.sol``/``Target.rs``, ``result.json``,
``metrics_iter_N.json``, ``checkpoint.json``, Lean/Foundry sources, Kani's
``kani_workspace``); they do
not alter pipeline behaviour.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.runners import RunSpec

Status = str  # passed | failed | unknown | skipped


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_text(path: Path, limit: int = 400_000) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return None


def _check(name: str, status: Status, detail: Optional[str] = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"name": name, "status": status}
    if detail:
        item["detail"] = detail[:1500]
    return item


def _tri(value: Any, ok: str = "", bad: str = "", none: str = "") -> Dict[str, Any]:
    """True/False/None -> passed/failed/unknown with per-outcome detail."""
    if value is True:
        return {"status": "passed", "detail": ok}
    if value is False:
        return {"status": "failed", "detail": bad}
    return {"status": "unknown", "detail": none}


def _stringify(value: Any, limit: int = 1500) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except Exception:  # pragma: no cover
            text = str(value)
    return text[:limit]


def _error_line(logs: List[Dict[str, Any]]) -> Optional[str]:
    for log in reversed(logs):
        message = log.get("message", "")
        if message.startswith(("PIPELINE EXECUTION ERROR", "LLM EXECUTION ERROR")):
            return message
    for log in reversed(logs):
        if log.get("level") == "error":
            return log.get("message")
    return None


class ResultMapper(ABC):
    @abstractmethod
    def map(self, spec: RunSpec, exit_code: int, logs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Return a GenerationResult dict, or None when nothing usable was produced."""

    @staticmethod
    def _tail_logs(logs: List[Dict[str, Any]], n: int = 200) -> List[Dict[str, Any]]:
        return logs[-n:]


# ── Solidity ─────────────────────────────────────────────────────────

class SolidityResultMapper(ResultMapper):
    EXTRA_SOURCES = [
        ("simulation_env/src/SafetyRules.sol", "solidity"),
        ("simulation_env/src/Invariant.t.sol", "solidity"),
        ("simulation_env/src/SemanticProbe.t.sol", "solidity"),
        ("simulation_env/script/Deploy.s.sol", "solidity"),
        ("simulation_env/src/Mocks.sol", "solidity"),
    ]

    def map(self, spec, exit_code, logs):
        ws = spec.workspace
        source = _read_text(ws / "Target.sol")
        if source is None:
            return None

        result_json = _read_json(ws / "result.json")
        iterations = int(result_json.get("iterations") or self._latest_iteration(ws) or 0)
        metrics = _read_json(ws / f"metrics_iter_{iterations}.json") if iterations else {}
        checkpoint = _read_json(ws / "checkpoint.json")

        files: List[Dict[str, Any]] = [{"path": "Target.sol", "language": "solidity", "content": source}]
        lean_files = self._lean_files(ws)
        for path, content in lean_files:
            files.append({"path": path, "language": "text", "content": content})
        for rel, language in self.EXTRA_SOURCES:
            content = _read_text(ws / rel)
            if content and content.strip():
                files.append({"path": rel, "language": language, "content": content})

        verification = self._verification(spec, result_json, metrics, logs)
        issues = self._issues(metrics, result_json)
        specification = self._specification(spec, lean_files, checkpoint, result_json)
        summary = self._summary(spec, result_json, metrics)
        report = {
            "filename": f"lever-{spec.run_id}-report.json",
            "mimeType": "application/json",
            "content": json.dumps({
                "run": {"id": spec.run_id, "name": spec.name, "target": spec.target, "mode": spec.cli_mode,
                        "max_iterations": spec.max_iters, "attack_rounds": spec.attack_rounds, "exit_code": exit_code},
                "result": result_json, "metrics": metrics,
                "selected_properties": checkpoint.get("selected_properties", []),
            }, indent=2, ensure_ascii=False, default=str),
        }
        return {
            "files": files, "specification": specification, "verification": verification,
            "issues": issues, "logs": self._tail_logs(logs), "summary": summary, "report": report,
        }

    @staticmethod
    def _latest_iteration(ws: Path) -> int:
        best = 0
        for path in ws.glob("metrics_iter_*.json"):
            try:
                best = max(best, int(path.stem.rsplit("_", 1)[1]))
            except ValueError:
                continue
        return best

    @staticmethod
    def _lean_files(ws: Path) -> List[tuple]:
        out = []
        for base in (ws / "lean_project", ws / "lean_project" / "Verification"):
            if not base.is_dir():
                continue
            for path in sorted(base.glob("*.lean")):
                content = _read_text(path)
                if content:
                    out.append((f"lean_project/{path.name}", content))
            if out:
                break
        return out

    def _verification(self, spec, result_json, metrics, logs) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []
        lean_enabled = spec.cli_mode in {"full", "lean_only"}
        dynamic_enabled = spec.cli_mode in {"full", "no_lean"}
        reason = result_json.get("reason", "")

        if metrics:
            compiled = metrics.get("compilation_success")
            if compiled is None:
                compiled = metrics.get("foundry_compile_pass")
            checks.append(_check("Solidity compilation (forge build)", **_tri(
                compiled if compiled is not None else True,
                "Target.sol compiled.", "Compiler errors reported.", "Compilation status not recorded.")))
        else:
            failed = "did not compile" in reason
            checks.append(_check("Solidity compilation (forge build)", "failed" if failed else "unknown",
                                 reason or _error_line(logs) or "No iteration metrics were written."))

        if lean_enabled:
            total = metrics.get("lean_theorems_total", 0)
            proven = metrics.get("lean_theorems_proven", 0)
            failed_theorems = metrics.get("lean_failed_theorems") or []
            detail = f"{proven}/{total} theorems proven." if total else "No theorems were generated."
            if failed_theorems:
                detail += " Unproven: " + ", ".join(_stringify(t, 80) for t in failed_theorems[:8])
            if not metrics:
                checks.append(_check("Lean 4 formal verification", "unknown", "Formal stage did not run."))
            else:
                checks.append(_check("Lean 4 formal verification",
                                     "passed" if metrics.get("formal_success") else "failed", detail))
        else:
            checks.append(_check("Lean 4 formal verification", "skipped", "Mode no_lean skips Lean proofs."))

        if dynamic_enabled:
            if not metrics:
                checks.append(_check("Foundry invariant fuzzing", "unknown", "Dynamic stage did not run."))
                checks.append(_check("Agent attack simulation (Anvil)", "unknown", "Dynamic stage did not run."))
            else:
                broken = metrics.get("broken_foundry_invariants") or []
                checks.append(_check("Foundry invariant fuzzing", **_tri(
                    metrics.get("foundry_test_pass"),
                    f"{metrics.get('foundry_fuzz_runs', 0)} fuzz runs, no invariant broken.",
                    "Broken invariants: " + ", ".join(_stringify(b, 100) for b in broken[:6]),
                    "Fuzz harness unavailable or infrastructure error.")))
                checks.append(_check("Agent attack simulation (Anvil)", **_tri(
                    metrics.get("agent_simulation_safe"),
                    f"{metrics.get('attack_episodes', 0)} attack episodes, no breach.",
                    f"{metrics.get('attack_breaches', 0)} breach(es) in {metrics.get('attack_episodes', 0)} episodes.",
                    "Attack simulation unavailable (infrastructure)." if metrics.get("attack_infra_broken") else "Not executed.")))
                if metrics.get("semantic_probe_enabled"):
                    checks.append(_check("Semantic probe tests", **_tri(
                        metrics.get("semantic_probe_safe"), "Semantic obligations held.",
                        "Semantic obligations violated.", "Probe not available.")))
                if metrics.get("slither_enabled"):
                    if metrics.get("slither_infra_broken"):
                        checks.append(_check("Slither static analysis", "unknown",
                                             "Slither unavailable: " + (metrics.get("slither_error") or "")[:300]))
                    else:
                        checks.append(_check("Slither static analysis", **_tri(
                            metrics.get("slither_pass"), "No high/medium findings.",
                            f"high={metrics.get('slither_high')} medium={metrics.get('slither_medium')} low={metrics.get('slither_low')}",
                            "No Slither verdict recorded.")))
                if metrics.get("llm_audit_enabled"):
                    checks.append(_check("LLM audit", **_tri(
                        metrics.get("llm_audit_pass"), "Auditor reported no blocking findings.",
                        f"high={metrics.get('llm_audit_high')} medium={metrics.get('llm_audit_medium')} low={metrics.get('llm_audit_low')}",
                        "Audit unavailable (infrastructure).")))
        else:
            checks.append(_check("Dynamic tests", "skipped", "Mode lean_only skips dynamic tests."))

        if not result_json:
            status, detail = "unknown", _error_line(logs) or "The pipeline exited before writing result.json."
        elif result_json.get("passed"):
            status, detail = "passed", f"{reason} (policy: {result_json.get('decision_policy')})"
        else:
            status, detail = "failed", f"{reason} (policy: {result_json.get('decision_policy')})"
        return {"status": status, "detail": detail, "checks": checks}

    @staticmethod
    def _issues(metrics, result_json) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        for i, finding in enumerate(metrics.get("llm_audit_findings") or []):
            if isinstance(finding, dict):
                issues.append({"id": f"audit-{i}", "title": finding.get("title") or "Audit finding",
                               "severity": finding.get("severity"), "description": _stringify(finding.get("evidence") or finding),
                               "file": "Target.sol"})
            else:
                issues.append({"id": f"audit-{i}", "title": "Audit finding", "description": _stringify(finding), "file": "Target.sol"})
        for i, theorem in enumerate(metrics.get("lean_failed_theorems") or []):
            issues.append({"id": f"lean-{i}", "title": "Unproven theorem", "severity": "formal",
                           "description": _stringify(theorem)})
        for i, inv in enumerate(metrics.get("broken_foundry_invariants") or []):
            issues.append({"id": f"fuzz-{i}", "title": "Broken invariant (Foundry)", "severity": "high",
                           "description": _stringify(inv), "file": "Target.sol"})
        for i, trace in enumerate(metrics.get("attack_traces") or []):
            issues.append({"id": f"attack-{i}", "title": "Attack breach (agent simulation)", "severity": "high",
                           "description": _stringify(trace, 2500), "file": "Target.sol"})
        for i, prop in enumerate(metrics.get("attack_derived_properties") or []):
            issues.append({"id": f"derived-{i}", "title": "Attack-derived property", "severity": "repair hint",
                           "description": _stringify(prop), "suggestion": "Enforce this property in the next repair iteration."})
        for i, failure in enumerate(metrics.get("semantic_probe_failures") or []):
            issues.append({"id": f"semantic-{i}", "title": "Semantic obligation violated", "severity": "high",
                           "description": _stringify(failure), "file": "Target.sol"})
        if metrics.get("slither_infra_broken") and metrics.get("slither_error"):
            issues.append({"id": "slither-infra", "title": "Slither not available", "severity": "infrastructure",
                           "description": _stringify(metrics.get("slither_error"), 600),
                           "suggestion": "Install Slither or set SLITHER_COMMAND to enable static analysis."})
        if not result_json.get("passed") and not metrics and result_json.get("reason"):
            issues.append({"id": "pipeline", "title": "Pipeline stopped early", "severity": "pipeline",
                           "description": result_json["reason"]})
        return issues

    @staticmethod
    def _specification(spec, lean_files, checkpoint, result_json) -> str:
        parts: List[str] = []
        selected = checkpoint.get("selected_properties") or []
        if selected:
            parts.append("Selected properties:")
            for prop in selected:
                if isinstance(prop, dict):
                    parts.append(f"- [{prop.get('id', '?')}] {prop.get('name', '')}: {prop.get('description', '')}")
                else:
                    parts.append(f"- {prop}")
            parts.append("")
        for texts_key, label in (("semantic_property_texts", "Semantic obligations"),):
            texts = checkpoint.get(texts_key) or []
            if texts:
                parts.append(f"{label}:")
                parts.extend(f"- {t}" for t in texts)
                parts.append("")
        for path, content in lean_files:
            parts.append(f"==== {path} ====")
            parts.append(content)
            parts.append("")
        if not parts:
            if spec.cli_mode == "no_lean":
                return "Formal specification skipped: mode no_lean does not generate a Lean model."
            return "No formal specification was produced. Reason: " + (result_json.get("reason") or "pipeline stopped before the formal stage.")
        return "\n".join(parts)

    @staticmethod
    def _summary(spec, result_json, metrics) -> str:
        lines = [
            f"Target: Solidity · mode {spec.cli_mode} · model {result_json.get('model') or spec.model or 'default'}",
            f"Result: {'PASSED' if result_json.get('passed') else 'FAILED' if result_json else 'UNKNOWN'} after "
            f"{result_json.get('iterations', '?')}/{result_json.get('max_iterations', spec.max_iters)} iteration(s).",
            f"Reason: {result_json.get('reason', 'no result.json written')}",
        ]
        if metrics:
            lines.append(
                f"Lean: {metrics.get('lean_theorems_proven', 0)}/{metrics.get('lean_theorems_total', 0)} theorems · "
                f"Foundry fuzz pass: {metrics.get('foundry_test_pass')} · attack breaches: {metrics.get('attack_breaches', 0)} · "
                f"Slither pass: {metrics.get('slither_pass')} · LLM audit pass: {metrics.get('llm_audit_pass')}"
            )
        lines.append(f"Workspace: {spec.workspace}")
        return "\n".join(lines)


# ── Solana (generation + Kani model checking) ────────────────────────

_KANI_STATUS = {"passed": "passed", "successful": "passed", "failed": "failed", "failure": "failed",
                "skipped": "skipped", "not_run": "skipped"}
_KANI_LOCATION = re.compile(r"src/lib\.rs:(\d+)")
_KANI_MESSAGE = re.compile(r"^(SOL-\d+)\s+\S+:\s*(.*?)(?:\s+@\s+(src/lib\.rs:\d+(?::\d+)?))?(?:\s+in function .*)?$")
KANI_LIB_PATH = "kani_workspace/src/lib.rs"


def _kani_status(value: Any) -> Status:
    return _KANI_STATUS.get(str(value or "").strip().lower(), "unknown")


def _count(value: Any) -> int:
    """Kani result fields are either counts or lists of check names."""
    if isinstance(value, (list, tuple, dict)):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _harness_label(harness: str) -> str:
    """``verification::sol_01_signer_check`` -> ``signer check``."""
    name = harness.rsplit("::", 1)[-1]
    parts = name.split("_", 2)
    return parts[2].replace("_", " ") if len(parts) == 3 and parts[0] == "sol" else name


class SolanaResultMapper(ResultMapper):
    NOT_IMPLEMENTED = "Not implemented yet — see SOLANA_VERIFICATION_ROADMAP.md."

    def map(self, spec, exit_code, logs):
        ws = spec.workspace
        source = _read_text(ws / "Target.rs")
        if source is None:
            return None
        result_json = _read_json(ws / "result.json")
        kani = (result_json.get("verification") or {}).get("kani")
        kani = kani if isinstance(kani, dict) else None
        kani_raw = _read_json(ws / "kani_workspace" / "kani_result.json") or \
            (_read_json(ws / "checkpoint.json").get("kani_result") or {})
        harness_src = _read_text(ws / "kani_workspace" / "src" / "lib.rs")

        files = [{"path": "programs/lever_target/src/lib.rs", "language": "rust", "content": source}]
        if harness_src:
            files.append({"path": KANI_LIB_PATH, "language": "rust", "content": harness_src})

        valid = bool(result_json.get("generation_valid"))
        checks = [
            _check("Anchor source generation", "passed" if valid else "failed",
                   "Structurally valid Anchor program (anchor_lang import + #[program])." if valid
                   else result_json.get("reason") or "Generated source failed the structural check."),
            _check("Anchor build (anchor build)", "skipped", self.NOT_IMPLEMENTED),
        ]
        checks.extend(self._kani_checks(spec, kani, kani_raw))
        checks.append(_check("Anchor tests (anchor test + local validator)", "skipped", self.NOT_IMPLEMENTED))

        verification = self._verification(valid, kani, result_json, checks)
        issues = self._issues(kani, kani_raw)
        summary = self._summary(spec, result_json, kani, kani_raw, valid)
        report = {
            "filename": f"lever-{spec.run_id}-report.json", "mimeType": "application/json",
            "content": json.dumps({
                "run": {"id": spec.run_id, "name": spec.name, "target": "solana", "mode": spec.cli_mode,
                        "max_iterations": spec.max_iters, "exit_code": exit_code},
                "result": result_json,
                "kani": {
                    **{k: kani_raw.get(k) for k in ("success", "fidelity", "harnesses", "properties", "infra_error")
                       if k in kani_raw},
                    **{k: _count(kani_raw.get(k)) for k in ("checks", "passed_checks", "failed_checks",
                                                             "undetermined_checks") if k in kani_raw},
                },
            }, indent=2, ensure_ascii=False, default=str),
        }
        return {
            "files": files,
            "specification": self._specification(kani, kani_raw, harness_src),
            "verification": verification, "issues": issues, "logs": self._tail_logs(logs),
            "summary": summary, "report": report,
        }

    # -- Kani -----------------------------------------------------------

    @staticmethod
    def _kani_checks(spec, kani, kani_raw) -> List[Dict[str, Any]]:
        name = "Kani formal verification (cargo kani)"
        if kani is None:
            if spec.cli_mode == "no_lean":
                return [_check(name, "skipped", "Mode no_lean skips formal verification.")]
            return [_check(name, "unknown", "No Kani result was recorded for this run.")]
        if kani_raw.get("infra_error"):
            return [_check(name, "unknown", "Kani could not run (infrastructure error); see logs.")]

        props: Dict[str, Any] = kani.get("properties") or {}
        statuses = {pid: _kani_status(st) for pid, st in props.items()}
        passed = sum(1 for s in statuses.values() if s == "passed")
        fidelity = kani.get("fidelity") or kani_raw.get("fidelity") or "unknown"
        detail = f"{passed}/{len(statuses)} properties proven (fidelity: {fidelity})."
        if _count(kani_raw.get("checks")):
            detail += (f" {_count(kani_raw.get('passed_checks'))}/{_count(kani_raw.get('checks'))} Kani checks passed"
                       f", {_count(kani_raw.get('failed_checks'))} failed.")
        if fidelity == "model":
            detail += " Harnesses check a plain-Rust model of the program, not the deployed Anchor code."
        checks = [_check(name, _kani_status(kani.get("status")), detail)]

        harness_names = {}
        for harness in (kani_raw.get("harnesses") or {}):
            pid = "SOL-" + harness.rsplit("::", 1)[-1].split("_")[1] if "sol_" in harness else None
            if pid:
                harness_names[pid] = _harness_label(harness)
        messages = {}
        for msg in kani.get("messages") or []:
            m = _KANI_MESSAGE.match(str(msg))
            if m:
                messages.setdefault(m.group(1), f"{m.group(2)} ({m.group(3) or 'location unknown'})")
        for pid in sorted(statuses):
            label = f"Kani · {pid}" + (f" ({harness_names[pid]})" if pid in harness_names else "")
            status = statuses[pid]
            if status == "passed":
                detail = "Harness verified: no counterexample within the explored bounds."
            elif status == "failed":
                detail = "Counterexample found: " + messages.get(pid, "see issues and Kani output.")
            else:
                detail = f"Kani reported '{props[pid]}'."
            checks.append(_check(label, status, detail))

        surface = kani.get("unverified_surface") or []
        if surface:
            checks.append(_check("Kani · not covered", "unknown",
                                 "No harness was written for: " + ", ".join(surface) + "."))
        return checks

    @staticmethod
    def _verification(valid, kani, result_json, checks) -> Dict[str, Any]:
        reason = result_json.get("reason") or ""
        if not result_json:
            return {"status": "unknown", "detail": "The pipeline exited before writing result.json.", "checks": checks}
        if not valid:
            return {"status": "failed", "detail": reason or "Generation failed.", "checks": checks}
        if kani is None:
            return {"status": "skipped", "checks": checks,
                    "detail": "Anchor program generated and validated. Kani, anchor build and local-validator "
                              "tests were not executed."}
        status = _kani_status(kani.get("status"))
        detail = {
            "passed": "All Kani harnesses verified. anchor build / anchor test are still pending (roadmap).",
            "failed": "Kani found counterexamples for at least one property. " + reason,
        }.get(status, "Kani verdict unavailable. " + reason)
        return {"status": status, "detail": detail.strip(), "checks": checks}

    @staticmethod
    def _issues(kani, kani_raw) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        seen = set()
        for i, cex in enumerate(kani_raw.get("counterexamples") or []):
            if not isinstance(cex, dict):
                continue
            pid = cex.get("property_id") or "Kani"
            seen.add(pid)
            loc = cex.get("location") or ""
            line_match = _KANI_LOCATION.search(loc)
            issue = {
                "id": f"kani-{pid}-{i}", "title": f"{pid}: Kani counterexample", "severity": "formal",
                "description": f"{cex.get('description') or 'Assertion failed'}\n"
                               f"Harness: {cex.get('harness', '?')}  ·  check: {cex.get('check', '?')}  ·  at {loc or '?'}",
                "file": KANI_LIB_PATH,
                "suggestion": "Inspect whether the program is missing this check or the harness asserts the wrong "
                              "thing (e.g. compares against a value it modified itself).",
            }
            if line_match:
                issue["line"] = int(line_match.group(1))
            issues.append(issue)
        for i, msg in enumerate((kani or {}).get("messages") or []):
            m = _KANI_MESSAGE.match(str(msg))
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            issue = {"id": f"kani-{m.group(1)}-msg{i}", "title": f"{m.group(1)}: Kani counterexample",
                     "severity": "formal", "description": str(msg), "file": KANI_LIB_PATH}
            line_match = _KANI_LOCATION.search(str(msg))
            if line_match:
                issue["line"] = int(line_match.group(1))
            issues.append(issue)
        surface = (kani or {}).get("unverified_surface") or []
        if surface:
            issues.append({"id": "kani-unverified", "title": "Properties without a Kani harness", "severity": "coverage",
                           "description": "Selected properties that Kani did not check: " + ", ".join(surface) + ".",
                           "suggestion": "Add Kani templates for these properties or verify them with anchor tests."})
        if kani_raw.get("infra_error"):
            issues.append({"id": "kani-infra", "title": "Kani did not run", "severity": "infrastructure",
                           "description": "cargo kani reported an infrastructure error; no verdict was produced.",
                           "suggestion": "Check that cargo-kani is installed (cargo kani --version)."})
        return issues

    @staticmethod
    def _specification(kani, kani_raw, harness_src) -> str:
        if not harness_src and kani is None:
            return "No Kani harnesses were generated for this run."
        parts: List[str] = []
        props = (kani or {}).get("properties") or {}
        if props:
            parts.append("Kani properties:")
            for pid in sorted(props):
                parts.append(f"- {pid}: {props[pid]}")
            parts.append("")
        surface = (kani or {}).get("unverified_surface") or []
        if surface:
            parts.append("Not covered by Kani: " + ", ".join(surface))
            parts.append("")
        if harness_src:
            parts.append(f"==== {KANI_LIB_PATH} ====")
            parts.append(harness_src)
        return "\n".join(parts)

    @staticmethod
    def _summary(spec, result_json, kani, kani_raw, valid) -> str:
        lines = [
            f"Target: Solana (Anchor) · mode {spec.cli_mode} · model {result_json.get('model') or spec.model or 'default'}",
            f"Generation: {'valid' if valid else 'invalid'} after {result_json.get('iterations', '?')}/"
            f"{result_json.get('max_iterations', spec.max_iters)} iteration(s).",
        ]
        if kani is None:
            lines.append("Kani: not run.")
        else:
            props = kani.get("properties") or {}
            passed = [p for p, s in sorted(props.items()) if _kani_status(s) == "passed"]
            failed = [p for p, s in sorted(props.items()) if _kani_status(s) == "failed"]
            lines.append(f"Kani: {_kani_status(kani.get('status')).upper()} · {len(passed)}/{len(props)} properties proven"
                         f" · fidelity {kani.get('fidelity') or kani_raw.get('fidelity') or '?'}")
            if failed:
                lines.append("Counterexamples: " + ", ".join(failed))
            if kani.get("unverified_surface"):
                lines.append("Not covered: " + ", ".join(kani["unverified_surface"]))
        lines.append("Anchor build / anchor test: pending (roadmap).")
        lines.append(f"Workspace: {spec.workspace}")
        return "\n".join(lines)


RESULT_MAPPERS: Dict[str, ResultMapper] = {
    "solidity": SolidityResultMapper(),
    "solana": SolanaResultMapper(),
}


def get_result_mapper(target: str) -> ResultMapper:
    try:
        return RESULT_MAPPERS[target]
    except KeyError as exc:
        raise ValueError(f"No result mapper for target '{target}'") from exc
