# ──────────────────────────────────────────────────────────────────────
# core/pipeline/kani_utils.py  — 🆕 NEW
# Kani Model Checker helpers for Solana formal verification.
#
# - Kani harness scaffolding
# - "cargo kani" output parsing
# - Counterexample extraction from Kani CBMC output
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Kani result blocks:
#   Check 2: check_add.arithmetic_overflow.1
#   	 - Status: FAILURE
#   	 - Description: "attempt to add with overflow"
#   	 - Location: src/lib.rs:13:17 in function check_add
_KANI_CHECK_RE = re.compile(
    r"^Check\s+(\d+):\s*(\S+)[ \t]*\n"
    r"\s*-\s*Status:\s*([A-Z_]+)[ \t]*"
    r"(?:\n\s*-\s*Description:\s*\"(.*)\"[ \t]*)?"
    r"(?:\n\s*-\s*Location:\s*([^\n]*))?",
    re.MULTILINE,
)
_KANI_HARNESS_RE = re.compile(r"^Checking harness\s+(\S+?)\.\.\.", re.MULTILINE)
_KANI_VERDICT_RE = re.compile(r"VERIFICATION:-\s*(SUCCESSFUL|FAILED)")


def generate_kani_harness_scaffold(
    program_code: str,
    property_name: str,
    property_description: str,
) -> str:
    """Generate a Kani verification harness skeleton for a given property.

    Parameters
    ----------
    program_code : str
        The Anchor program Rust source.
    property_name : str
        Short identifier (e.g. ``"SOL_01_signer_check"``).
    property_description : str
        Human-readable description of the property to verify.

    Returns
    -------
    str
        Rust source text containing the ``#[kani::proof]`` harness.
    """
    # TODO: Implement harness generation (LLM-assisted or template-based)
    raise NotImplementedError("generate_kani_harness_scaffold — implementation pending")


def parse_kani_output(stdout: str, stderr: str, returncode: int) -> Dict[str, Any]:
    """Parse ``cargo kani`` output into a structured result dict.

    Returns
    -------
    dict
        Keys: ``success``, ``verified``, ``failed``, ``errors``, ``counterexamples``.
    """
    combined = f"{stdout}\n{stderr}".replace("\r\n", "\n")

    # Split into per-harness sections ("Checking harness <name>...").
    starts = list(_KANI_HARNESS_RE.finditer(combined))
    sections = [
        (m.group(1), combined[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(combined)])
        for i, m in enumerate(starts)
    ] or [("", combined)]

    checks: List[Dict[str, Any]] = []
    harnesses: Dict[str, str] = {}
    for harness, section in sections:
        for m in _KANI_CHECK_RE.finditer(section):
            checks.append({
                "harness": harness,
                "id": int(m.group(1)),
                "name": m.group(2),
                "status": m.group(3),
                "description": m.group(4) or "",
                "location": (m.group(5) or "").strip(),
            })
        verdict = _KANI_VERDICT_RE.search(section)
        if harness and verdict:
            harnesses[harness] = verdict.group(1)

    # Kani prints one "VERIFICATION:- SUCCESSFUL|FAILED" line per harness.
    verdicts = _KANI_VERDICT_RE.findall(combined)
    passed_checks = [c["name"] for c in checks if c["status"] == "SUCCESS"]
    failed_checks = [c["name"] for c in checks if c["status"] == "FAILURE"]
    undetermined_checks = [c["name"] for c in checks if c["status"] == "UNDETERMINED"]
    success = (
        returncode == 0
        and "SUCCESSFUL" in verdicts
        and "FAILED" not in verdicts
        and not failed_checks
        and not undetermined_checks
    )

    return {
        "success": success,
        "verified": len(passed_checks),
        "failed": len(failed_checks),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "undetermined_checks": undetermined_checks,
        "checks": checks,
        "harnesses": harnesses,
        "errors": [] if success else [combined[-2000:]],
        "counterexamples": [],  # TODO: Extract CBMC counterexamples (needs concrete playback)
    }


def extract_kani_counterexample(kani_output: str) -> Optional[Dict[str, Any]]:
    """Extract a concrete counterexample from Kani CBMC output.

    Returns
    -------
    dict | None
        Structured counterexample with variable assignments, or None.
    """
    # TODO: Parse CBMC trace output for concrete counterexample values
    #       Kani outputs "TRACE" sections with variable assignments
    if "Trace:" not in kani_output:
        return None

    # Placeholder: return raw trace section
    trace_start = kani_output.index("Trace:")
    trace_text = kani_output[trace_start : trace_start + 3000]
    return {
        "source": "kani",
        "raw_trace": trace_text,
        "assignments": {},  # TODO: Parse individual assignments
    }
