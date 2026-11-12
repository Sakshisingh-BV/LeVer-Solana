"""Tests for the Kani stage of workflow_solana_generate_only.

The adapter is a fake: no LLM, no cargo, no Kani install.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.kani_templates import KANI_ELIGIBLE, UNVERIFIED_SURFACE
from core.pipeline.checkpoint import CheckpointManager
from core.pipeline.context import PipelineContext
from core.pipeline.workflows import (
    DEFAULT_SOLANA_KANI_PROPERTIES,
    workflow_solana_generate_only,
)

CODE = "use anchor_lang::prelude::*;\ndeclare_id!(\"x\");\n#[program]\npub mod p {}\n"
SPEC = "#[cfg(kani)]\n#[kani::proof]\nfn sol_07_arithmetic_overflow() {}\n"


class FakeAdapter:
    """Stands in for SolanaAdapter; each test configures the Kani outcome."""

    model_name = "fake-model"

    def __init__(self, spec=SPEC, ok=True, messages=(), kani_result=None,
                 fidelity="real", verify_exc=None):
        self.spec = spec
        self.ok = ok
        self.messages = list(messages)
        self.kani_result = kani_result
        self.fidelity = fidelity
        self.verify_exc = verify_exc
        self.last_fidelity = None
        self.last_kani_result = None
        self.spec_calls = []
        self.verify_calls = []

    def generate_code(self, requirement, properties, *, feedback_constraints=None, **kw):
        return CODE

    def repair_code(self, current_code, feedback, **kw):
        return CODE

    def is_valid_source(self, code):
        return bool(code)

    def generate_formal_spec(self, code, properties, **kw):
        self.spec_calls.append((code, list(properties)))
        if self.spec:
            self.last_fidelity = self.fidelity
        return self.spec

    def verify_spec(self, spec, workspace, **kw):
        self.verify_calls.append((spec, workspace))
        if self.verify_exc is not None:
            raise self.verify_exc
        result = dict(self.kani_result or {})
        result.setdefault("infra_error", False)
        result.setdefault("fidelity", self.last_fidelity or "unknown")
        result.setdefault("properties", {})
        self.last_kani_result = result
        return self.ok, list(self.messages)


def _props(**statuses):
    return {pid.replace("_", "-"): {"status": s, "harnesses": {}} for pid, s in statuses.items()}


class KaniWorkflowTestCase(unittest.TestCase):

    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="lever_kani_wf_")
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        checkpoint = CheckpointManager(os.path.join(self.workspace, "checkpoint.json"))
        self.ctx = PipelineContext(self.workspace, checkpoint)

    def run_workflow(self, adapter, mode="full"):
        passed = workflow_solana_generate_only(
            ctx=self.ctx, adapter=adapter, requirement="a counter program", mode=mode, max_iters=2
        )
        with open(os.path.join(self.workspace, "result.json"), encoding="utf-8") as f:
            return passed, json.load(f)

    def assert_common_shape(self, kani):
        for key in ("status", "fidelity", "properties", "messages", "unverified_surface"):
            self.assertIn(key, kani)
        self.assertEqual(kani["unverified_surface"], list(UNVERIFIED_SURFACE))

    # ── defaults ─────────────────────────────────────────────────────
    def test_default_properties_are_kani_eligible(self):
        self.assertEqual(DEFAULT_SOLANA_KANI_PROPERTIES, ("SOL-01", "SOL-02", "SOL-04", "SOL-07", "SOL-08"))
        self.assertTrue(all(pid in KANI_ELIGIBLE for pid in DEFAULT_SOLANA_KANI_PROPERTIES))

    # ── passed ───────────────────────────────────────────────────────
    def test_passed(self):
        all_ok = {pid: {"status": "SUCCESSFUL", "harnesses": {}} for pid in DEFAULT_SOLANA_KANI_PROPERTIES}
        adapter = FakeAdapter(ok=True, kani_result={"properties": all_ok})
        passed, result = self.run_workflow(adapter)

        self.assertTrue(passed)
        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["status"], "passed")
        self.assertEqual(kani["fidelity"], "real")
        self.assertEqual(kani["properties"], {pid: "passed" for pid in DEFAULT_SOLANA_KANI_PROPERTIES})
        self.assertEqual(kani["messages"], [])
        self.assertNotIn("warning", kani)
        self.assertEqual(adapter.spec_calls, [(CODE, list(DEFAULT_SOLANA_KANI_PROPERTIES))])
        self.assertEqual(adapter.verify_calls, [(SPEC, self.workspace)])
        self.assertEqual(self.ctx.feedback_constraints, [])
        self.assertEqual(self.ctx.checkpoint.load_stage("kani_result"), kani)

    def test_lean_only_mode_runs_kani(self):
        adapter = FakeAdapter(ok=True)
        _, result = self.run_workflow(adapter, mode="lean_only")
        self.assertEqual(result["verification"]["kani"]["status"], "passed")
        self.assertEqual(len(adapter.verify_calls), 1)

    # ── failed ───────────────────────────────────────────────────────
    def test_failed_adds_feedback_constraints(self):
        messages = [
            "SOL-07 sol_07_arithmetic_overflow: attempt to add with overflow @ src/lib.rs:10",
            "SOL-01 sol_01_signer_check: assertion failed @ src/lib.rs:20",
        ]
        adapter = FakeAdapter(
            ok=False,
            messages=messages,
            kani_result={"properties": _props(SOL_07="FAILED", SOL_01="FAILED", SOL_02="SUCCESSFUL")},
        )
        passed, result = self.run_workflow(adapter)

        self.assertTrue(passed)  # Kani is non-blocking for the generation-only policy
        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["status"], "failed")
        self.assertEqual(kani["messages"], messages)
        self.assertEqual(kani["properties"], {
            "SOL-01": "failed",
            "SOL-02": "passed",
            "SOL-04": "undetermined",
            "SOL-07": "failed",
            "SOL-08": "undetermined",
        })
        self.assertEqual(self.ctx.feedback_constraints, [f"Kani: {m}" for m in messages])

    # ── infra_error ──────────────────────────────────────────────────
    def test_infra_error_adds_no_feedback_constraints(self):
        adapter = FakeAdapter(
            ok=False,
            messages=["infra_error: cargo-kani not found"],
            kani_result={"infra_error": True},
        )
        passed, result = self.run_workflow(adapter)

        self.assertTrue(passed)
        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["status"], "infra_error")
        self.assertEqual(kani["messages"], ["infra_error: cargo-kani not found"])
        self.assertEqual(set(kani["properties"].values()), {"undetermined"})
        self.assertEqual(self.ctx.feedback_constraints, [])

    def test_verify_spec_exception_does_not_crash(self):
        adapter = FakeAdapter(verify_exc=RuntimeError("boom"))
        passed, result = self.run_workflow(adapter)

        self.assertTrue(passed)
        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["status"], "infra_error")
        self.assertEqual(len(kani["messages"]), 1)
        self.assertIn("RuntimeError: boom", kani["messages"][0])
        self.assertEqual(self.ctx.feedback_constraints, [])

    def test_generate_formal_spec_exception_does_not_crash(self):
        adapter = FakeAdapter()
        adapter.generate_formal_spec = lambda code, props, **kw: (_ for _ in ()).throw(ValueError("llm down"))
        passed, result = self.run_workflow(adapter)

        self.assertTrue(passed)
        kani = result["verification"]["kani"]
        self.assertEqual(kani["status"], "infra_error")
        self.assertIn("ValueError: llm down", kani["messages"][0])
        self.assertEqual(adapter.verify_calls, [])
        self.assertEqual(self.ctx.feedback_constraints, [])

    # ── skipped ──────────────────────────────────────────────────────
    def test_skipped_when_spec_empty(self):
        adapter = FakeAdapter(spec="")
        passed, result = self.run_workflow(adapter)

        self.assertTrue(passed)
        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["status"], "skipped")
        self.assertEqual(kani["reason"], "no eligible properties")
        self.assertEqual(adapter.verify_calls, [])
        self.assertEqual(self.ctx.feedback_constraints, [])

    def test_skipped_in_no_lean_mode(self):
        adapter = FakeAdapter()
        passed, result = self.run_workflow(adapter, mode="no_lean")

        self.assertTrue(passed)
        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["status"], "skipped")
        self.assertEqual(adapter.spec_calls, [])
        self.assertEqual(adapter.verify_calls, [])

    # ── scaffold ─────────────────────────────────────────────────────
    def test_scaffold_fidelity_records_warning(self):
        adapter = FakeAdapter(
            ok=False,
            fidelity="scaffold",
            messages=["SOL-07 sol_07_arithmetic_overflow: scaffold placeholder @ src/lib.rs:5"],
            kani_result={"properties": _props(SOL_07="FAILED")},
        )
        _, result = self.run_workflow(adapter)

        kani = result["verification"]["kani"]
        self.assert_common_shape(kani)
        self.assertEqual(kani["fidelity"], "scaffold")
        self.assertIn("warning", kani)
        self.assertIn("proves nothing", kani["warning"])
        self.assertEqual(kani["status"], "failed")

    def test_scaffold_failure_adds_no_feedback_constraints(self):
        messages = ["SOL-07 sol_07_arithmetic_overflow: scaffold placeholder @ src/lib.rs:5"]
        for fidelity, expect_feedback in (("scaffold", False), ("real", True), ("model", True)):
            with self.subTest(fidelity=fidelity):
                self.setUp()
                adapter = FakeAdapter(
                    ok=False,
                    fidelity=fidelity,
                    messages=messages,
                    kani_result={"properties": _props(SOL_07="FAILED")},
                )
                before = list(self.ctx.feedback_constraints)
                _, result = self.run_workflow(adapter)

                kani = result["verification"]["kani"]
                self.assertEqual(kani["status"], "failed")
                self.assertEqual(kani["fidelity"], fidelity)
                self.assertEqual(kani["messages"], messages)
                if expect_feedback:
                    self.assertEqual(self.ctx.feedback_constraints, before + [f"Kani: {m}" for m in messages])
                    self.assertNotIn("warning", kani)
                else:
                    self.assertEqual(self.ctx.feedback_constraints, before)
                    self.assertIn("warning", kani)


if __name__ == "__main__":
    unittest.main()
