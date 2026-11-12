# ──────────────────────────────────────────────────────────────────────
# core/adapters/solana_adapter.py  (Blue Box)
# SolanaAdapter(TargetAdapter)
#
# Phase 1 (implemented):
#   generate_code()   → core.solana_agents.AnchorCoder.generate_anchor_code()
#   repair_code()     → core.solana_agents.AnchorCoder.repair_anchor_code()
#   is_valid_source() → core.pipeline.solana_utils.is_plausible_anchor_source()
#
# Phase 2 (implemented):
#   verify_spec()            → "cargo kani" on a standalone crate (pipeline/kani_utils.py)
#   extract_counterexample() → kani_utils.extract_kani_counterexample()
#
# Phase 2 (planned — see SOLANA_VERIFICATION_ROADMAP.md, NOT implemented):
#   check_compilation()      → "anchor build"
#   generate_formal_spec()   → Kani harness generation (pipeline/kani_utils.py)
#   generate_test_harness()  → Anchor TS/Rust tests
#   run_tests()              → "anchor test" + solana-test-validator
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

from core.adapters.base import TargetAdapter

ROADMAP = "see SOLANA_VERIFICATION_ROADMAP.md (Phase 2)"

#: Default wall-clock limit for one ``cargo kani`` run, in seconds.
DEFAULT_KANI_TIMEOUT = 300
#: Environment variable that overrides DEFAULT_KANI_TIMEOUT.
KANI_TIMEOUT_ENV = "KANI_TIMEOUT"
#: Flags passed to every ``cargo kani`` run.
KANI_ARGS = ("--output-format", "regular", "-Z", "concrete-playback", "--concrete-playback=print")


def kani_command(cli: str) -> List[str]:
    """Build the argv prefix for ``cargo kani`` from a CARGO_KANI_CLI setting.

    Accepts ``"cargo kani"`` (run through cargo) or ``"cargo-kani"`` / a path to it
    (run the plugin binary directly). Cargo runs a plugin as ``cargo-kani kani <args>``,
    so when the binary is called directly the ``kani`` subcommand word is added to
    match exactly what cargo would pass.
    """
    cli = (cli or "").strip() or "cargo-kani"
    parts = [cli] if os.path.isfile(cli) else cli.split()
    leaf = os.path.basename(parts[-1]).lower()
    if leaf.endswith(".exe"):
        leaf = leaf[:-4]
    if leaf == "cargo-kani":
        parts.append("kani")
    return parts


def _resolve_timeout(timeout: Optional[float]) -> float:
    """*timeout* if given, else $KANI_TIMEOUT, else DEFAULT_KANI_TIMEOUT."""
    if timeout is not None:
        return float(timeout)
    raw = os.getenv(KANI_TIMEOUT_ENV, "").strip()
    try:
        value = float(raw) if raw else DEFAULT_KANI_TIMEOUT
    except ValueError:
        value = DEFAULT_KANI_TIMEOUT
    return value if value > 0 else DEFAULT_KANI_TIMEOUT


def _fmt_seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


class SolanaAdapter(TargetAdapter):
    """Adapter for Solana / Anchor targets (Anchor CLI + Kani Model Checker)."""

    target = "solana"
    toolchain = "Anchor CLI + solana-test-validator + Kani"
    required_tools = ("anchor", "solana", "cargo", "cargo-kani")
    optional_tools = ("solana-test-validator",)
    implemented_stages = ("generate", "repair", "validate", "verify", "counterexample")

    def __init__(self, model_name: Optional[str] = None, **kwargs: Any):
        self.model_name = model_name or os.getenv("LLM_MODEL") or None
        self._coder = None
        #: Fidelity of the last generated Kani spec (set by the spec stage), if known.
        self.last_fidelity: Optional[str] = None
        #: Contents of kani_result.json from the last verify_spec() call.
        self.last_kani_result: Optional[Dict[str, Any]] = None

    @property
    def coder(self):
        if self._coder is None:
            from core.solana_agents import AnchorCoder
            self._coder = AnchorCoder(model_name=self.model_name)
        return self._coder

    # ── Code Generation ──────────────────────────────────────────────
    def generate_code(self, requirement, properties, *, feedback_constraints=None, **kwargs) -> str:
        return self.coder.generate_anchor_code(requirement, properties or [], feedback_constraints=feedback_constraints)

    def repair_code(self, current_code, feedback, *, properties=None, **kwargs) -> str:
        return self.coder.repair_anchor_code(current_code, feedback, properties=properties)

    # ── Validation ───────────────────────────────────────────────────
    def is_valid_source(self, code: str) -> bool:
        from core.pipeline.solana_utils import is_plausible_anchor_source
        return is_plausible_anchor_source(code)

    def check_compilation(self, code: str, workspace: str) -> Tuple[bool, str]:
        raise NotImplementedError(f"SolanaAdapter.check_compilation (anchor build) — {ROADMAP}")

    # ── Formal Verification ──────────────────────────────────────────
    def generate_formal_spec(self, code, properties, **kwargs) -> str:
        raise NotImplementedError(f"SolanaAdapter.generate_formal_spec (Kani harness) — {ROADMAP}")

    def verify_spec(
        self, spec: str, workspace: str, *, timeout: Optional[float] = None, **kwargs: Any
    ) -> Tuple[bool, List[str]]:
        """Run ``cargo kani`` on *spec* (the Kani crate's ``src/lib.rs``).

        The crate is written to ``<workspace>/kani_workspace`` and the result is saved
        there as ``kani_result.json`` (also kept in ``self.last_kani_result``).

        Returns ``(True, [])`` only when Kani reports success. Otherwise returns
        ``(False, messages)`` with one ``"<SOL-XX> <harness>: <description> @ <location>"``
        message per failed check. A missing ``cargo-kani`` or a timeout is an
        infrastructure error (``"infra_error: ..."`` message, ``infra_error`` true in
        the JSON), never a verification failure.

        *timeout* (seconds) defaults to $KANI_TIMEOUT, else 300.
        """
        from core import solana_config
        from core.pipeline.kani_utils import parse_kani_output, write_kani_crate

        crate_dir = write_kani_crate(os.path.join(workspace, "kani_workspace"), spec)
        limit = _resolve_timeout(timeout)
        cmd = kani_command(solana_config.CARGO_KANI_CLI) + list(KANI_ARGS)

        infra_message: Optional[str] = None
        try:
            proc = subprocess.run(
                cmd,
                cwd=crate_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=limit,
            )
        except FileNotFoundError:
            infra_message = "infra_error: cargo-kani not found"
        except subprocess.TimeoutExpired:
            infra_message = f"infra_error: kani timeout after {_fmt_seconds(limit)}s"

        if infra_message is not None:
            result: Dict[str, Any] = {
                "success": False,
                "verified": 0,
                "failed": 0,
                "passed_checks": [],
                "failed_checks": [],
                "undetermined_checks": [],
                "checks": [],
                "harnesses": {},
                "errors": [infra_message],
                "counterexamples": [],
            }
            messages = [infra_message]
        else:
            result = parse_kani_output(proc.stdout or "", proc.stderr or "", proc.returncode)
            messages = [] if result["success"] else _kani_failure_messages(result, proc.returncode)

        result["infra_error"] = infra_message is not None
        result["fidelity"] = self.last_fidelity or "unknown"
        result["properties"] = _kani_property_map(result)
        result["command"] = cmd

        with open(os.path.join(crate_dir, "kani_result.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(result, f, indent=2)
        self.last_kani_result = result

        if infra_message is None and result["success"]:
            return True, []
        return False, messages

    # ── Testing / Simulation ─────────────────────────────────────────
    def generate_test_harness(self, code, properties, **kwargs) -> str:
        raise NotImplementedError(f"SolanaAdapter.generate_test_harness (Anchor tests) — {ROADMAP}")

    def run_tests(self, workspace: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError(f"SolanaAdapter.run_tests (anchor test) — {ROADMAP}")

    # ── Counterexample Extraction ────────────────────────────────────
    def extract_counterexample(self, tool_output: str) -> Optional[Dict[str, Any]]:
        """Counterexample for the first failing Kani check in *tool_output*, or None."""
        from core.pipeline.kani_utils import extract_kani_counterexample
        return extract_kani_counterexample(tool_output) or None


# ── Kani result helpers ──────────────────────────────────────────────

def _kani_failure_messages(result: Dict[str, Any], returncode: int) -> List[str]:
    """``"<SOL-XX> <harness>: <description> @ <location>"`` per failed check.

    If no check failed but Kani still did not succeed, undetermined checks are
    reported instead (prefixed ``UNDETERMINED``), else one generic message, so a
    failed run never comes back with an empty message list.
    """
    from core.pipeline.kani_utils import harness_property_id

    def fmt(check: Dict[str, Any], prefix: str = "") -> str:
        pid = harness_property_id(check["harness"]) or "UNKNOWN"
        return f"{prefix}{pid} {check['harness']}: {check['description']} @ {check['location']}"

    failed = [fmt(c) for c in result["checks"] if c["status"] == "FAILURE"]
    if failed:
        return failed
    undetermined = [fmt(c, "UNDETERMINED ") for c in result["checks"] if c["status"] == "UNDETERMINED"]
    if undetermined:
        return undetermined
    return [f"kani: verification did not succeed (exit code {returncode}, no failing check parsed)"]


def _kani_property_map(result: Dict[str, Any]) -> Dict[str, Any]:
    """``{"SOL-XX": {"status": "SUCCESSFUL"|"FAILED"|"UNKNOWN", "harnesses": {name: verdict}}}``.

    A property is FAILED if any of its harnesses failed and SUCCESSFUL only if all of
    them were verified. Harnesses that don't map to a Kani-eligible property are left out.
    """
    from core.pipeline.kani_utils import harness_property_id

    verdicts: Dict[str, str] = dict(result.get("harnesses", {}))
    for check in result.get("checks", []):
        if check["harness"]:
            verdicts.setdefault(check["harness"], "UNKNOWN")

    props: Dict[str, Any] = {}
    for harness, verdict in verdicts.items():
        pid = harness_property_id(harness)
        if pid is not None:
            props.setdefault(pid, {"status": "UNKNOWN", "harnesses": {}})["harnesses"][harness] = verdict
    for entry in props.values():
        vs = set(entry["harnesses"].values())
        entry["status"] = "FAILED" if "FAILED" in vs else ("SUCCESSFUL" if vs == {"SUCCESSFUL"} else "UNKNOWN")
    return props
