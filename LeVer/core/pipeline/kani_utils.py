# ──────────────────────────────────────────────────────────────────────
# core/pipeline/kani_utils.py  — 🆕 NEW
# Kani Model Checker helpers for Solana formal verification.
#
# - Kani harness scaffolding
# - "cargo kani" output parsing
# - Counterexample extraction from Kani CBMC output
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.kani_templates import DEFAULT_UNWIND, KANI_ELIGIBLE, get_kani_template

#: Text of the always-failing assertion in an unfilled scaffold. A check whose
#: description contains it means "harness never written", not "property violated".
UNFILLED_MARKER = "LEVER_UNFILLED_HARNESS"

# Kani result blocks:
#   Check 2: check_add.arithmetic_overflow.1
#   	 - Status: FAILURE
#   	 - Description: "attempt to add with overflow"
#   	 - Location: src/lib.rs:13:17 in function check_add
# Check names can contain spaces (e.g. "core::num::<impl u64>::checked_add.arithmetic_overflow.1"),
# so the name runs to the end of the line.
_KANI_CHECK_RE = re.compile(
    r"^Check[ \t]+(\d+):[ \t]*(\S[^\n]*?)[ \t]*\n"
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
    """Generate a deterministic, fail-closed Kani harness skeleton for one property.

    This is the fallback used when no LLM-written harness is available. The body is a
    single always-failing assertion, so an unfilled scaffold reports FAILURE under
    ``cargo kani``; it can never pass vacuously and count as a proof.

    Parameters
    ----------
    program_code : str
        The Anchor program Rust source. Only used to list candidate instruction
        handlers in a comment; none of it is copied into the harness.
    property_name : str
        A Kani-eligible property id in any common spelling (``"SOL-07"``,
        ``"sol_07"``, ``"SOL_01_signer_check"``).
    property_description : str
        Human-readable description of the property; when empty, the template's
        prompt snippet from properties/solana.json is used.

    Returns
    -------
    str
        Rust source text containing one ``#[cfg(kani)] #[kani::proof]`` harness named
        ``sol_XX_<slug>``.

    Raises
    ------
    ValueError
        If *property_name* is unknown or not Kani-eligible (unverified surface).
        No harness is produced for such properties.
    """
    template = get_kani_template(property_name)
    if template is None:
        raise ValueError(
            f"No Kani harness for {property_name!r}: not a Kani-eligible Solana property "
            f"(eligible: {', '.join(KANI_ELIGIBLE)})"
        )

    description = (property_description or "").strip() or template.prompt_snippet
    lines = [f"// LeVer Kani scaffold: {template.property_id} {template.name}"]
    lines += [
        "// FAIL-CLOSED: the assertion below always fails under `cargo kani`.",
        "// Replace the body with a model of the program logic (kani::any() inputs,",
        "// kani::assume() preconditions) and assertions for the property.",
    ]
    lines += [f"// {line}".rstrip() for line in description.replace("\r", "").split("\n")]
    handlers = _anchor_handler_names(program_code or "")
    if handlers:
        lines.append(f"// Candidate instruction handlers: {', '.join(handlers)}")
    lines += [
        "#[cfg(kani)]",
        "#[kani::proof]",
        f"#[kani::unwind({DEFAULT_UNWIND})]",
        f"fn {template.harness_name}() {{",
        f'    assert!(false, "{UNFILLED_MARKER}: {template.property_id} harness not filled in");',
        "}",
    ]
    return "\n".join(lines) + "\n"


_HANDLER_RE = re.compile(r"\bpub\s+fn\s+(\w+)\s*(?:<[^>{]*>)?\s*\(\s*\w+\s*:\s*Context\s*<")


def _anchor_handler_names(program_code: str) -> List[str]:
    """Names of ``pub fn name(ctx: Context<...>, ...)`` handlers, in source order."""
    names: List[str] = []
    for m in _HANDLER_RE.finditer(_mask_rust(program_code)):
        if m.group(1) not in names:
            names.append(m.group(1))
    return names


# ── Rust source helpers ──────────────────────────────────────────────

_RAW_STR_RE = re.compile(r'b?r(#*)"')
_CHAR_RE = re.compile(r"b?'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F]{1,6}\}|.)|[^'\\\n])'")


def _mask_rust(code: str) -> str:
    """Return *code* with comments and string/char literals blanked out.

    Length and newlines are preserved, so offsets into the result are valid in
    *code*. Lifetimes (``'a``) are left alone. Used so that braces or keywords inside
    comments and literals don't affect brace matching and token checks.
    """
    out = list(code)
    n = len(code)

    def blank(start: int, end: int) -> None:
        for k in range(start, end):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        prev_ident = i > 0 and (code[i - 1].isalnum() or code[i - 1] == "_")
        if code.startswith("//", i):
            end = code.find("\n", i)
            end = n if end == -1 else end
        elif code.startswith("/*", i):
            depth, end = 1, i + 2
            while end < n and depth:
                if code.startswith("/*", end):
                    depth, end = depth + 1, end + 2
                elif code.startswith("*/", end):
                    depth, end = depth - 1, end + 2
                else:
                    end += 1
        elif not prev_ident and _RAW_STR_RE.match(code, i):
            m = _RAW_STR_RE.match(code, i)
            close = code.find('"' + m.group(1), m.end())
            end = n if close == -1 else close + 1 + len(m.group(1))
        elif code[i] == '"' or (code.startswith('b"', i) and not prev_ident):
            end = i + (2 if code[i] == "b" else 1)
            while end < n and code[end] != '"':
                end += 2 if code[end] == "\\" else 1
            end = min(end + 1, n)
        elif code[i] in "'b" and not (code[i] == "b" and prev_ident) and _CHAR_RE.match(code, i):
            end = _CHAR_RE.match(code, i).end()
        else:
            i += 1
            continue
        blank(i, end)
        i = end
    return "".join(out)


def _matching_brace(masked: str, open_idx: int) -> Optional[int]:
    depth = 0
    for k in range(open_idx, len(masked)):
        if masked[k] == "{":
            depth += 1
        elif masked[k] == "}":
            depth -= 1
            if depth == 0:
                return k
    return None


_LOGIC_MOD_RE = re.compile(r"\bpub(?:\s*\(\s*crate\s*\))?\s+mod\s+logic\s*\{")
_USE_RE = re.compile(r"\buse\s+(?:::\s*)?(\w+)")
_STD_ROOTS = {"std", "core", "alloc", "self"}

# Anything that ties the module to Anchor/Solana or to items outside the module,
# so it would not compile (or would mean something else) as a standalone crate.
_LOGIC_FORBIDDEN = [
    re.compile(p) for p in (
        r"\banchor_lang\b", r"\banchor_spl\b", r"\bsolana_program\b", r"\bspl_\w+",
        r"\bborsh\b",
        r"\bsuper\s*::", r"\bcrate\s*::", r"\bextern\s+crate\b",
        r"\bctx\b", r"\bContext\s*<", r"\bAccountInfo\b", r"\bAccountLoader\b",
        r"\b(?:Account|Signer|Program|Sysvar|UncheckedAccount|Interface|InterfaceAccount)\s*<",
        r"\bPubkey\b", r"\bProgramResult\b", r"\bProgramError\b",
        r"\binvoke(?:_signed)?\s*\(",
        r"\b(?:require\w*|err|error|msg|emit|declare_id)\s*!",
        r"#\s*\[\s*(?:account|program|error_code|event|derive\s*\([^)]*\bAccounts\b)",
        r"\bResult\s*<[^<>,]*>",  # Anchor's one-parameter Result<T> alias
    )
]


def extract_logic_module(code: str) -> Optional[str]:
    """Return the program's dependency-free ``pub mod logic { ... }`` block, or None.

    The hybrid Kani path verifies this module's real code (copied verbatim into the
    standalone Kani crate) instead of an LLM-written copy. It is accepted only if it
    references nothing from Anchor/Solana and nothing outside itself (``super::``,
    ``crate::``, non-std ``use``), so it compiles in a crate with no dependencies.
    Comments and string literals are ignored when checking.

    Returns None when there is no inline ``logic`` module, its braces don't balance,
    or it uses a forbidden item.
    """
    if not code:
        return None
    masked = _mask_rust(code)
    m = _LOGIC_MOD_RE.search(masked)
    if not m:
        return None
    close = _matching_brace(masked, m.end() - 1)
    if close is None:
        return None
    body = masked[m.end():close]
    if any(p.search(body) for p in _LOGIC_FORBIDDEN):
        return None
    if any(u.group(1) not in _STD_ROOTS for u in _USE_RE.finditer(body)):
        return None
    return code[m.start():close + 1]


# ── Kani crate ───────────────────────────────────────────────────────

KANI_CRATE_CARGO_TOML = """\
[package]
name = "lever-kani"
version = "0.1.0"
edition = "2021"
publish = false

[lib]
path = "src/lib.rs"

# Standalone on purpose: no anchor-lang / solana-program under Kani's toolchain.
[dependencies]

# Keep this crate out of any enclosing Cargo workspace.
[workspace]

[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ["cfg(kani)"] }
"""


def write_kani_crate(kani_dir: str, lib_rs: str) -> str:
    """Write a dependency-free Kani crate (``Cargo.toml`` + ``src/lib.rs``) into *kani_dir*.

    Existing ``Cargo.toml`` and ``src/lib.rs`` are overwritten; other files are left
    alone. Returns the crate's absolute path.

    Raises ValueError if *lib_rs* is empty.
    """
    if not lib_rs or not lib_rs.strip():
        raise ValueError("write_kani_crate: lib_rs is empty")
    src_dir = os.path.join(kani_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(kani_dir, "Cargo.toml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(KANI_CRATE_CARGO_TOML)
    with open(os.path.join(src_dir, "lib.rs"), "w", encoding="utf-8", newline="\n") as f:
        f.write(lib_rs if lib_rs.endswith("\n") else lib_rs + "\n")
    return os.path.abspath(kani_dir)


_HARNESS_NAME_RE = re.compile(r"^sol_(\d{2})(?:_\w*)?$")


def harness_property_id(harness_name: str) -> Optional[str]:
    """Map a harness name to its property id: ``"sol_07_arithmetic_overflow"`` → ``"SOL-07"``.

    Module paths as printed by Kani (``"proofs::sol_07_x"``) are accepted. Returns None
    for names that don't follow the ``sol_XX_`` convention and for properties that are
    not Kani-eligible, so a stray harness can never be reported as verifying an
    unverified-surface property.
    """
    if not isinstance(harness_name, str):
        return None
    leaf = harness_name.strip().rsplit("::", 1)[-1]
    m = _HARNESS_NAME_RE.match(leaf)
    if not m:
        return None
    pid = f"SOL-{m.group(1)}"
    return pid if pid in KANI_ELIGIBLE else None


def parse_kani_output(stdout: str, stderr: str, returncode: int) -> Dict[str, Any]:
    """Parse ``cargo kani`` output into a structured result dict.

    Returns
    -------
    dict
        Keys: ``success``, ``verified``, ``failed``, ``errors``, ``counterexamples``.
    """
    combined = f"{stdout}\n{stderr}".replace("\r\n", "\n")

    checks: List[Dict[str, Any]] = []
    harnesses: Dict[str, str] = {}
    counterexamples: List[Dict[str, Any]] = []
    for harness, section in _harness_sections(combined):
        for m in _KANI_CHECK_RE.finditer(section):
            checks.append({
                "harness": harness,
                "id": int(m.group(1)),
                "name": m.group(2),
                "status": m.group(3),
                "description": _clean_description(m.group(4)),
                "location": (m.group(5) or "").strip(),
            })
        cex = _section_counterexample(harness, section, combined)
        if cex is not None:
            counterexamples.append(cex)
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
        "counterexamples": counterexamples,
    }


def extract_kani_counterexample(kani_output: str) -> Optional[Dict[str, Any]]:
    """Extract the counterexample for the first failing harness in Kani output.

    The failing check is the first ``Check N:`` block with ``Status: FAILURE``.
    Concrete input values come from the ``Concrete playback unit test for
    `<harness>``` block (printed with ``--concrete-playback=print``): each
    ``// <number><suffix>`` comment above a byte vector gives one ``kani::any()``
    value, in order. Kani does not name the variables, so they are stored by
    position as ``input_0``, ``input_1``, ... with decimal string values.
    Without a playback block, ``assignments`` is ``{}``.

    Returns
    -------
    dict | None
        ``{"source", "harness", "property_id", "check", "description", "location",
        "assignments", "raw_trace"}``, or None when no check failed.
    """
    if not kani_output:
        return None
    combined = kani_output.replace("\r\n", "\n")
    for harness, section in _harness_sections(combined):
        cex = _section_counterexample(harness, section, combined)
        if cex is not None:
            return cex
    return None


def _harness_sections(combined: str) -> List[Tuple[str, str]]:
    """Split output into ``(harness, text)`` pairs at each "Checking harness <name>..." line.

    Output with no such line is returned as one section with harness ``""``.
    """
    starts = list(_KANI_HARNESS_RE.finditer(combined))
    return [
        (m.group(1), combined[m.end(): starts[i + 1].start() if i + 1 < len(starts) else len(combined)])
        for i, m in enumerate(starts)
    ] or [("", combined)]


def _clean_description(desc: Optional[str]) -> str:
    """Drop the extra quote pair Kani prints around assert messages.

    Kani 0.68 prints an ``assert!(cond, "msg")`` check as ``Description: ""msg""``;
    the check regex removes the outer pair, leaving ``"msg"``, which this unwraps.
    """
    desc = desc or ""
    if len(desc) >= 2 and desc.startswith('"') and desc.endswith('"'):
        desc = desc[1:-1]
    return desc


# One concrete value per line in a playback test, e.g. "        // 9223372036854775808ul".
# Doc comments ("/// ...") don't match: the value must start right after "//".
_PLAYBACK_VALUE_RE = re.compile(r"^[ \t]*//[ \t]*(-?\d+)[A-Za-z0-9_]*[ \t]*$", re.MULTILINE)
_IN_FUNCTION_RE = re.compile(r"\s+in function\s+.*$")


def _playback_block(combined: str, harness: str) -> Optional[str]:
    """The fenced "Concrete playback unit test for `<harness>`:" block, or None."""
    if not harness:
        return None
    m = re.search(
        r"^Concrete playback unit test for `" + re.escape(harness) + r"`:[ \t]*\n```[^\n]*\n.*?^```",
        combined,
        re.MULTILINE | re.DOTALL,
    )
    return m.group(0) if m else None


def _section_counterexample(harness: str, section: str, combined: str) -> Optional[Dict[str, Any]]:
    """Counterexample for one harness's output section, or None if none of its checks failed."""
    failing = next(
        (m for m in _KANI_CHECK_RE.finditer(section) if m.group(3) == "FAILURE"),
        None,
    )
    if failing is None:
        return None

    playback = _playback_block(combined, harness)
    assignments: Dict[str, str] = {}
    raw_trace = failing.group(0).strip()
    if playback:
        values = _PLAYBACK_VALUE_RE.findall(playback)
        assignments = {f"input_{i}": str(int(v)) for i, v in enumerate(values)}
        raw_trace += "\n\n" + playback.strip()

    return {
        "source": "kani",
        "harness": harness,
        "property_id": harness_property_id(harness),
        "check": failing.group(2),
        "description": _clean_description(failing.group(4)),
        "location": _IN_FUNCTION_RE.sub("", (failing.group(5) or "").strip()),
        "assignments": assignments,
        "raw_trace": raw_trace,
    }
