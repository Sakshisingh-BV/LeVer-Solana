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
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

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
