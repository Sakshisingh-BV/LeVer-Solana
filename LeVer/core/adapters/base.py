# ──────────────────────────────────────────────────────────────────────
# core/adapters/base.py  — 🆕 NEW
# TargetAdapter Abstract Base Class (ABC)
#
# Every chain-specific adapter (Solidity, Solana, Move, …) MUST subclass
# this ABC and implement every @abstractmethod.
#
# The main pipeline calls ONLY these methods — it never talks to
# forge/anchor/lean/kani directly.
# ──────────────────────────────────────────────────────────────────────

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class TargetAdapter(ABC):
    """Universal interface between the LeVer core engine and a target chain.

    Diagram mapping (Blue Box — Target Adapter Interface):
        generate_code()           → LLM agent produces smart-contract source
        repair_code()             → LLM agent patches source given feedback
        is_valid_source()         → Quick sanity-check on generated code
        check_compilation()       → Build / compile the source
        generate_formal_spec()    → Produce formal-verification spec
        verify_spec()             → Run formal-verification tooling
        generate_test_harness()   → Create fuzz / invariant test code
        run_tests()               → Execute tests (local validator / fork)
        extract_counterexample()  → Parse test/verifier output for failures
    """

    # ── Adapter metadata (used by the factory, CLI routing and the HTTP API) ──
    #: Registry key, e.g. "solidity" / "solana".
    target: str = ""
    #: Human-readable toolchain summary.
    toolchain: str = ""
    #: CLI tools that must be on PATH for the full pipeline.
    required_tools: Tuple[str, ...] = ()
    #: Tools that improve coverage but whose absence the pipeline tolerates.
    optional_tools: Tuple[str, ...] = ()
    #: Pipeline stages this adapter can execute today.
    implemented_stages: Tuple[str, ...] = ()

    ALL_STAGES: Tuple[str, ...] = (
        "generate", "repair", "validate", "compile",
        "formal_spec", "verify", "test_harness", "run_tests", "counterexample",
    )

    def describe(self) -> Dict[str, Any]:
        """Capability report: toolchain presence and implemented stages (no LLM calls)."""
        import shutil

        tools = {name: shutil.which(name) is not None for name in self.required_tools}
        optional = {name: shutil.which(name) is not None for name in self.optional_tools}
        missing_stages = [s for s in self.ALL_STAGES if s not in self.implemented_stages]
        return {
            "target": self.target,
            "toolchain": self.toolchain,
            "tools": tools,
            "optional_tools": optional,
            "implemented_stages": list(self.implemented_stages),
            "missing_stages": missing_stages,
            # "available": the adapter can at least generate code for this target.
            "available": "generate" in self.implemented_stages,
            # "pipeline_ready": every stage is implemented and every required tool is installed.
            "pipeline_ready": not missing_stages and all(tools.values()),
        }

    # ── Code Generation ──────────────────────────────────────────────

    @abstractmethod
    def generate_code(
        self,
        requirement: str,
        properties: List[Dict],
        *,
        feedback_constraints: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Generate smart-contract source code from a natural-language requirement.

        Parameters
        ----------
        requirement : str
            The user's free-text security requirement.
        properties : list[dict]
            Selected safety properties from the properties/ catalogue.
        feedback_constraints : list[str] | None
            Repair hints accumulated from prior iterations.

        Returns
        -------
        str
            The generated source code (Solidity / Rust+Anchor / Move …).
        """
        ...

    @abstractmethod
    def repair_code(
        self,
        current_code: str,
        feedback: str,
        *,
        properties: Optional[List[Dict]] = None,
        **kwargs: Any,
    ) -> str:
        """Patch *current_code* using *feedback* from verification / testing.

        Returns
        -------
        str
            The repaired source code.
        """
        ...

    # ── Validation ───────────────────────────────────────────────────

    @abstractmethod
    def is_valid_source(self, code: str) -> bool:
        """Quick, regex-level plausibility check (no external tools).

        Examples
        --------
        - Solidity: ``"pragma solidity" in code``
        - Solana:   ``"use anchor_lang" in code``
        """
        ...

    @abstractmethod
    def check_compilation(self, code: str, workspace: str) -> Tuple[bool, str]:
        """Compile / build the source and return (success, diagnostics).

        Parameters
        ----------
        code : str
            Source text.
        workspace : str
            Absolute path to the run's workspace directory.

        Returns
        -------
        tuple[bool, str]
            ``(True, "")`` on success; ``(False, error_output)`` on failure.
        """
        ...

    # ── Formal Verification ──────────────────────────────────────────

    @abstractmethod
    def generate_formal_spec(
        self,
        code: str,
        properties: List[Dict],
        **kwargs: Any,
    ) -> str:
        """Produce a formal specification (Lean / Kani harness / …).

        Returns
        -------
        str
            The formal spec source text.
        """
        ...

    @abstractmethod
    def verify_spec(self, spec: str, workspace: str) -> Tuple[bool, List[str]]:
        """Run the formal verifier and return (all_passed, error_list).

        Parameters
        ----------
        spec : str
            Formal spec source text (Lean 4 / Kani Rust / …).
        workspace : str
            Run workspace path.

        Returns
        -------
        tuple[bool, list[str]]
            ``(True, [])`` when all obligations discharge;
            ``(False, ["err1", …])`` otherwise.
        """
        ...

    # ── Testing / Simulation ─────────────────────────────────────────

    @abstractmethod
    def generate_test_harness(
        self,
        code: str,
        properties: List[Dict],
        **kwargs: Any,
    ) -> str:
        """Create fuzz / invariant / integration test code.

        Returns
        -------
        str
            Test harness source (Foundry test / Anchor TS test / …).
        """
        ...

    @abstractmethod
    def run_tests(self, workspace: str, **kwargs: Any) -> Dict[str, Any]:
        """Execute the test suite and return a structured result dict.

        Expected keys in the result dict (at minimum):
            ``success``  : bool
            ``passed``   : int
            ``failed``   : int
            ``details``  : str   — raw tool output
        """
        ...

    # ── Counterexample Extraction ────────────────────────────────────

    @abstractmethod
    def extract_counterexample(self, tool_output: str) -> Optional[Dict[str, Any]]:
        """Parse verifier / test output for a concrete counterexample.

        Returns
        -------
        dict | None
            Structured counterexample data, or ``None`` if none found.
        """
        ...
