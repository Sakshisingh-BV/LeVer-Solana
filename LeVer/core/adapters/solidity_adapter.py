# ──────────────────────────────────────────────────────────────────────
# core/adapters/solidity_adapter.py  (Yellow Box)
# SolidityAdapter(TargetAdapter)
#
# WRAPS existing LeVer code — no modification to original modules:
#   generate_code()         → core.agents.SolidityCoder.generate_modern_code / generate_code
#   repair_code()           → core.agents.SolidityCoder.generate_code (repair prompt)
#   is_valid_source()       → core.pipeline.solidity_utils.is_plausible_solidity_source()
#   check_compilation()     → core.simulator.SimulationRunner.check_compilation() (forge build)
#   generate_formal_spec()  → core.agents.LeanFormalizer.formalize_definitions()
#   verify_spec()           → core.formal_verifier.FormalVerifier.verify_file() (Lean 4)
#   generate_test_harness() → core.agents.EnvironmentArchitect.generate_safety_rules/generate_fuzz_test
#   run_tests()             → core.simulator.SimulationRunner.run_fuzz_and_attack() (forge test + Anvil)
#   extract_counterexample()→ core.structured_logging.parse_foundry_output()
#
# Agents are created lazily so describe()/capabilities never build LLM clients.
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.adapters.base import TargetAdapter


def _property_texts(properties: Optional[List[Any]]) -> List[str]:
    texts: List[str] = []
    for prop in properties or []:
        if isinstance(prop, dict):
            name = prop.get("name") or prop.get("id") or "property"
            body = prop.get("invariant_template") or prop.get("description") or ""
            texts.append(f"{name}: {body}".strip(": "))
        elif prop:
            texts.append(str(prop))
    return texts


class SolidityAdapter(TargetAdapter):
    """Adapter for Solidity / EVM targets (Foundry + Lean 4).

    Thin wrapper around the **existing** LeVer modules; it only delegates.
    """

    target = "solidity"
    toolchain = "Foundry (forge/anvil) + Lean 4 + Slither"
    required_tools = ("forge", "anvil", "lean")
    optional_tools = ("slither",)
    implemented_stages = TargetAdapter.ALL_STAGES

    def __init__(self, model_name: Optional[str] = None, attack_rounds: int = 3, **kwargs: Any):
        self.model_name = model_name or os.getenv("LLM_MODEL") or None
        self.attack_rounds = attack_rounds
        self._coder = None
        self._formalizer = None
        self._architect = None

    # ── lazy agents ──────────────────────────────────────────────────
    @property
    def coder(self):
        if self._coder is None:
            from core.agents import SolidityCoder
            self._coder = SolidityCoder(model_name=self.model_name)
        return self._coder

    @property
    def formalizer(self):
        if self._formalizer is None:
            from core.agents import LeanFormalizer
            self._formalizer = LeanFormalizer(model_name=self.model_name)
        return self._formalizer

    @property
    def architect(self):
        if self._architect is None:
            from core.agents import EnvironmentArchitect
            self._architect = EnvironmentArchitect(model_name=self.model_name)
        return self._architect

    def _simulator(self, workspace: str):
        from core.simulator import SimulationRunner
        return SimulationRunner(root_dir=os.path.join(workspace, "simulation_env"), attack_rounds=self.attack_rounds)

    # ── Code Generation ──────────────────────────────────────────────
    def generate_code(self, requirement, properties, *, feedback_constraints=None, **kwargs) -> str:
        constraints = list(feedback_constraints or [])
        if not constraints:
            return self.coder.generate_modern_code(requirement)
        constraints += [f"Enforce property: {t}" for t in _property_texts(properties)]
        return self.coder.generate_code(requirement, constraints)

    def repair_code(self, current_code, feedback, *, properties=None, **kwargs) -> str:
        requirement = kwargs.get("requirement", "")
        repair_prompt = f"""
        [ORIGINAL REQUIREMENT]
        {requirement}

        [CURRENT SOLIDITY]
        {current_code}

        Return a complete repaired Solidity implementation that still satisfies
        the original requirement and addresses every supplied constraint.
        """
        constraints = [feedback] + [f"Enforce property: {t}" for t in _property_texts(properties)]
        return self.coder.generate_code(repair_prompt, [c for c in constraints if c])

    # ── Validation ───────────────────────────────────────────────────
    def is_valid_source(self, code: str) -> bool:
        from core.pipeline.solidity_utils import is_plausible_solidity_source
        return bool(is_plausible_solidity_source(code))

    def check_compilation(self, code: str, workspace: str) -> Tuple[bool, str]:
        sim = self._simulator(workspace)
        try:
            sim.initialize_environment(code, "")
            return sim.check_compilation()
        finally:
            sim.close()

    # ── Formal Verification ──────────────────────────────────────────
    def generate_formal_spec(self, code, properties, **kwargs) -> str:
        return self.formalizer.formalize_definitions(
            code, _property_texts(properties),
            error_feedback=kwargs.get("error_feedback", ""),
            theorem_budget=kwargs.get("theorem_budget", 0),
        )

    def verify_spec(self, spec: str, workspace: str) -> Tuple[bool, List[str]]:
        from core.formal_verifier import FormalVerifier
        verifier = FormalVerifier(project_root=os.path.join(workspace, "lean_project"))
        verifier.save_file("Definitions.lean", spec)
        errors = verifier.verify_file("Definitions.lean")
        return (not errors), list(errors)

    # ── Testing / Simulation ─────────────────────────────────────────
    def generate_test_harness(self, code, properties, **kwargs) -> str:
        safety_code = kwargs.get("safety_code")
        if not safety_code:
            safety_code, _ = self.architect.generate_safety_rules(code, _property_texts(properties))
        return self.architect.generate_fuzz_test(
            code, safety_code,
            error_feedback=kwargs.get("error_feedback", ""),
            previous_code=kwargs.get("previous_code", ""),
            semantic_context=kwargs.get("semantic_context", ""),
        )

    def run_tests(self, workspace: str, **kwargs) -> Dict[str, Any]:
        """kwargs mirror SimulationRunner.run_fuzz_and_attack(target_sol, mocks_sol, safety_sol,
        deploy_script, regex_config, interface_desc, safety_check_logic)."""
        sim = self._simulator(workspace)
        try:
            result = sim.run_fuzz_and_attack(
                kwargs.get("target_sol", ""), kwargs.get("mocks_sol", ""), kwargs.get("safety_sol", ""),
                kwargs.get("deploy_script", ""), kwargs.get("regex_config", {}),
                kwargs.get("interface_desc", ""), kwargs.get("safety_check_logic", ""),
            ) or {}
        finally:
            sim.close()
        breaches = int(result.get("breaches", 0) or 0)
        return {
            "success": bool(result.get("safe")),
            "passed": int(result.get("attack_episodes", 0) or 0) - breaches,
            "failed": breaches,
            "details": str(result.get("log", result)),
            "raw": result,
        }

    # ── Counterexample Extraction ────────────────────────────────────
    def extract_counterexample(self, tool_output: str) -> Optional[Dict[str, Any]]:
        from core.structured_logging import parse_foundry_output
        parsed = parse_foundry_output(tool_output or "", "", 1)
        failing = re.findall(r"\[FAIL[^\]]*\]\s*(\S+)", tool_output or "")
        counterexample = re.search(r"Counterexample:?\s*(.+)", tool_output or "")
        if not failing and not counterexample:
            return None
        return {
            "source": "foundry",
            "failing_tests": failing,
            "counterexample": counterexample.group(1).strip() if counterexample else None,
            "parsed": parsed,
        }
