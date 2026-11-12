# ──────────────────────────────────────────────────────────────────────
# core/solana_agents.py
# AnchorCoder: LLM agent for Solana / Anchor / Rust code generation.
#
# Reuses core.agents.BaseAgent (same OpenAI-compatible client, retries,
# fence/<think> stripping, GLOBAL_LOGGER agent logging) — mirroring SolidityCoder.
#
# Methods:
#   generate_anchor_code()  → Produce Anchor program (lib.rs) from requirement
#   repair_anchor_code()    → Patch Anchor program given verification feedback
#
# KaniHarnessWriter: LLM agent that writes the standalone Kani crate lib.rs
#   write_kani_harness()    → harnesses for Kani-eligible properties; falls back
#                             to fail-closed scaffolds on LLM error / invalid output
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core.agents import BaseAgent


def _properties_text(properties: Optional[List[Any]]) -> str:
    lines: List[str] = []
    for prop in properties or []:
        if isinstance(prop, dict):
            lines.append(
                f"- [{prop.get('id', '?')}] {prop.get('name', '')}: "
                f"{prop.get('invariant_template') or prop.get('description', '')}"
            )
        elif prop:
            lines.append(f"- {prop}")
    return "\n".join(lines) if lines else "None"


class AnchorCoder(BaseAgent):
    """LLM-backed agent for generating and repairing Solana Anchor programs."""

    SYSTEM_PROMPT = (
        "You are a Solana Anchor + Rust Security Engineer.\n"
        "You write production-grade Anchor programs using the anchor_lang framework.\n"
        "Your code must include:\n"
        "  - Signer validation on every privileged instruction\n"
        "  - Account ownership checks via Anchor constraints\n"
        "  - PDA derivation with bump validation\n"
        "  - CPI program-ID validation\n"
        "  - checked_* arithmetic to prevent overflow\n"
        "  - Proper error handling with custom error enums\n"
        "\n"
        "[OUTPUT RULES]\n"
        "1. Return ONE complete `lib.rs` for a single Anchor program (anchor-lang 0.30.x).\n"
        "2. Start with `use anchor_lang::prelude::*;` and a `declare_id!(\"...\");` line.\n"
        "3. Include the `#[program]` module, every `#[derive(Accounts)]` context struct,\n"
        "   `#[account]` state structs with explicit space constants, and an `#[error_code]` enum.\n"
        "4. No tests, no client code, no Markdown explanations — Rust source only.\n"
    )

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, **kwargs: Any):
        super().__init__(model_name=model_name, api_key=api_key, base_url=base_url)

    def generate_anchor_code(self, requirement: str, properties: List[Dict], *,
                             feedback_constraints: Optional[List[str]] = None) -> str:
        """Generate a complete Anchor program (lib.rs contents) from a requirement."""
        constraints = "\n".join(f"- {c}" for c in (feedback_constraints or [])) or "None"
        user_prompt = f"""
        [REQUIREMENT]
        {requirement}

        [SAFETY PROPERTIES TO ENFORCE]
        {_properties_text(properties)}

        [CONSTRAINTS FROM PREVIOUS ATTEMPTS]
        {constraints}

        [TASK]
        Implement the program described above as a single Anchor `lib.rs`.
        """
        print("   AnchorCoder is generating the Anchor program...")
        return self._query_llm(self.SYSTEM_PROMPT, user_prompt)

    def repair_anchor_code(self, current_code: str, feedback: str, *,
                           properties: Optional[List[Dict]] = None) -> str:
        """Repair an existing Anchor program based on verification/test feedback."""
        user_prompt = f"""
        [CURRENT ANCHOR PROGRAM]
        {current_code}

        [VERIFICATION / TEST FEEDBACK]
        {feedback}

        [SAFETY PROPERTIES TO ENFORCE]
        {_properties_text(properties)}

        [TASK]
        Return the complete repaired `lib.rs`. Make minimal changes that address every
        feedback item while preserving the program's intent and account layout.
        """
        print("   AnchorCoder is repairing the Anchor program...")
        return self._query_llm(self.SYSTEM_PROMPT, user_prompt)


# ── Kani harness writer ──────────────────────────────────────────────

_SOL_HARNESS_FN_RE = re.compile(r"\bfn\s+(sol_(\d+)\w*)\s*(?:<[^>{]*>)?\s*\(", re.IGNORECASE)
_KANI_PROOF_RE = re.compile(r"#\s*\[\s*kani\s*::\s*proof\s*\]")
_ANCHOR_LANG_RE = re.compile(r"\banchor_lang\b")


def kani_property_ids(properties: Optional[List[Any]]) -> List[str]:
    """Normalized, de-duplicated Kani-eligible ids (``"SOL-07"``) from dicts or strings, in order.

    Unknown ids and unverified-surface properties are dropped.
    """
    from core.kani_templates import KANI_ELIGIBLE, normalize_property_id

    ids: List[str] = []
    for prop in properties or []:
        raw = prop.get("id") if isinstance(prop, dict) else prop
        pid = normalize_property_id(raw) if isinstance(raw, str) else None
        if pid in KANI_ELIGIBLE and pid not in ids:
            ids.append(pid)
    return ids


def validate_kani_harness(source: str, property_ids: List[str], *,
                          logic_module: Optional[str] = None) -> List[str]:
    """Problems with an LLM-written Kani ``lib.rs``; an empty list means it is acceptable.

    Checks (comments and string literals are ignored):
      - at least one ``#[kani::proof]``;
      - exactly one ``fn sol_XX_...`` harness for each requested property id;
      - no ``sol_XX_`` harness for any other (unrequested or unknown) property id;
      - no ``anchor_lang`` reference (the Kani crate has no dependencies);
      - when *logic_module* is given, it appears verbatim (ignoring whitespace), so a
        "real" fidelity claim really verifies the program's own code.
    """
    from core.pipeline.kani_utils import _mask_rust

    if not source or not source.strip():
        return ["empty output"]
    masked = _mask_rust(source)
    errors: List[str] = []
    if not _KANI_PROOF_RE.search(masked):
        errors.append("no #[kani::proof] harness")
    if _ANCHOR_LANG_RE.search(masked):
        errors.append("references anchor_lang")

    found: Dict[str, List[str]] = {}
    for m in _SOL_HARNESS_FN_RE.finditer(masked):
        found.setdefault(f"SOL-{int(m.group(2)):02d}", []).append(m.group(1))
    for pid in property_ids:
        count = len(found.get(pid, []))
        if count != 1:
            errors.append(f"expected exactly one {pid} harness, found {count}")
    unknown = sorted(name for pid, names in found.items() if pid not in property_ids for name in names)
    if unknown:
        errors.append(f"harnesses for unrequested/unknown properties: {', '.join(unknown)}")

    if logic_module is not None:
        def squash(s: str) -> str:
            return re.sub(r"\s+", "", s)
        if squash(logic_module) not in squash(source):
            errors.append("logic module not included verbatim")
    return errors


class KaniHarnessWriter(BaseAgent):
    """LLM agent that writes a standalone Kani crate ``lib.rs`` for Solana properties.

    Fail-closed: if the LLM errors or its output fails validate_kani_harness(), the
    result is the deterministic always-failing scaffold for each property
    (``generate_kani_harness_scaffold``) and ``last_used_fallback`` is set.
    """

    SYSTEM_PROMPT = (
        "You are a Rust formal-verification engineer writing Kani model-checking harnesses\n"
        "for Solana programs.\n"
        "\n"
        "[OUTPUT RULES]\n"
        "1. Return ONE complete `lib.rs` for a standalone crate with NO dependencies:\n"
        "   never reference anchor_lang, anchor_spl, solana_program or borsh.\n"
        "2. Put every harness behind `#[cfg(kani)]` and mark it `#[kani::proof]`;\n"
        "   add `#[kani::unwind(N)]` when the harness contains loops.\n"
        "3. Write exactly one harness per requested property, named exactly as given\n"
        "   (`sol_XX_<slug>`). Write no other function whose name starts with `sol_`.\n"
        "4. Use `kani::any()` for inputs and `kani::assume()` for preconditions, then assert\n"
        "   the property. Never write a harness that passes vacuously.\n"
        "5. No Markdown explanations — Rust source only.\n"
        "6. Snapshot rule for expected values and 'nothing changed' checks: first finish\n"
        "   ALL setup edits to the inputs (e.g. clearing a signer flag), THEN copy them\n"
        "   (`let accts_before = accts; let state_before = state;`), THEN make the call.\n"
        "   Compare post-call values only against that snapshot, never against an\n"
        "   earlier baseline (like a `good` setup) that the setup has since changed.\n"
        "   Never modify a snapshot or expected value after the call.\n"
    )

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None,
                 base_url: Optional[str] = None, **kwargs: Any):
        super().__init__(model_name=model_name, api_key=api_key, base_url=base_url)
        #: True when the last write_kani_harness() call returned the scaffold fallback.
        self.last_used_fallback: bool = False
        #: Why the fallback was used (LLM error or validation problems), else empty.
        self.last_errors: List[str] = []

    def write_kani_harness(self, program_code: str, properties: List[Any], *,
                           logic_module: Optional[str] = None) -> str:
        """Return the Kani crate's ``lib.rs`` text for the Kani-eligible *properties*.

        With *logic_module* (from ``extract_logic_module``) the LLM must copy it
        verbatim and harness its ``logic::`` functions; without it, the LLM writes a
        plain-struct model of the program. Ineligible/unknown properties are ignored;
        returns "" when none remain.
        """
        from core.kani_templates import get_kani_template

        self.last_used_fallback = False
        self.last_errors = []
        ids = kani_property_ids(properties)
        if not ids:
            return ""
        templates = [get_kani_template(pid) for pid in ids]

        prop_lines = "\n".join(
            f"- {t.property_id} {t.name} -> harness `fn {t.harness_name}()`\n  "
            + t.prompt_snippet.replace("\n", "\n  ")
            for t in templates
        )
        if logic_module is not None:
            model_task = (
                "The program has a dependency-free `logic` module. Copy it VERBATIM (unchanged)\n"
                "into lib.rs and write the harnesses against `logic::` functions, so Kani checks\n"
                "the program's real code.\n\n"
                f"[LOGIC MODULE]\n{logic_module}"
            )
        else:
            model_task = (
                "The program has no dependency-free `logic` module. Write a plain-struct model:\n"
                "plain Rust structs (u64 balances, [u8; 32] keys, bool flags) mirroring the\n"
                "accounts and handler logic relevant to each property, then harness that model."
            )
        user_prompt = f"""
        [ANCHOR PROGRAM]
        {program_code}

        [PROPERTIES - ONE HARNESS EACH]
        {prop_lines}

        [MODEL]
        {model_task}

        [TASK]
        Return the complete standalone Kani `lib.rs`.
        """
        print("   KaniHarnessWriter is writing Kani harnesses...")
        try:
            source = self._query_llm(self.SYSTEM_PROMPT, user_prompt) or ""
            errors = validate_kani_harness(source, ids, logic_module=logic_module)
        except Exception as e:  # any LLM failure -> fail closed
            source, errors = "", [f"LLM error: {e}"]
        if not errors:
            return source if source.endswith("\n") else source + "\n"

        print(f"   KaniHarnessWriter output rejected ({'; '.join(errors)}); using fail-closed scaffolds.")
        self.last_used_fallback = True
        self.last_errors = errors
        return self.scaffold(program_code, ids)

    @staticmethod
    def scaffold(program_code: str, property_ids: List[str]) -> str:
        """Fail-closed lib.rs: one always-failing scaffold harness per property id."""
        from core.pipeline.kani_utils import generate_kani_harness_scaffold

        parts = ["// LeVer Kani crate: fail-closed scaffolds (no valid LLM harness available).\n"]
        parts += [generate_kani_harness_scaffold(program_code, pid, "") for pid in property_ids]
        return "\n".join(parts)
