# ──────────────────────────────────────────────────────────────────────
# core/adapters/solana_adapter.py  (Blue Box)
# SolanaAdapter(TargetAdapter)
#
# Phase 1 (implemented):
#   generate_code()   → core.solana_agents.AnchorCoder.generate_anchor_code()
#   repair_code()     → core.solana_agents.AnchorCoder.repair_anchor_code()
#   is_valid_source() → core.pipeline.solana_utils.is_plausible_anchor_source()
#
# Phase 2 (planned — see SOLANA_VERIFICATION_ROADMAP.md, NOT implemented):
#   check_compilation()      → "anchor build"
#   generate_formal_spec()   → Kani harness generation (pipeline/kani_utils.py)
#   verify_spec()            → "cargo kani"
#   generate_test_harness()  → Anchor TS/Rust tests
#   run_tests()              → "anchor test" + solana-test-validator
#   extract_counterexample() → Kani trace / program-log parser
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from core.adapters.base import TargetAdapter

ROADMAP = "see SOLANA_VERIFICATION_ROADMAP.md (Phase 2)"


class SolanaAdapter(TargetAdapter):
    """Adapter for Solana / Anchor targets (Anchor CLI + Kani Model Checker)."""

    target = "solana"
    toolchain = "Anchor CLI + solana-test-validator + Kani"
    required_tools = ("anchor", "solana", "cargo", "cargo-kani")
    optional_tools = ("solana-test-validator",)
    implemented_stages = ("generate", "repair", "validate")

    def __init__(self, model_name: Optional[str] = None, **kwargs: Any):
        self.model_name = model_name or os.getenv("LLM_MODEL") or None
        self._coder = None

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

    def verify_spec(self, spec: str, workspace: str) -> Tuple[bool, List[str]]:
        raise NotImplementedError(f"SolanaAdapter.verify_spec (cargo kani) — {ROADMAP}")

    # ── Testing / Simulation ─────────────────────────────────────────
    def generate_test_harness(self, code, properties, **kwargs) -> str:
        raise NotImplementedError(f"SolanaAdapter.generate_test_harness (Anchor tests) — {ROADMAP}")

    def run_tests(self, workspace: str, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError(f"SolanaAdapter.run_tests (anchor test) — {ROADMAP}")

    # ── Counterexample Extraction ────────────────────────────────────
    def extract_counterexample(self, tool_output: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError(f"SolanaAdapter.extract_counterexample — {ROADMAP}")
