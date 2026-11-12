"""
Tests for SolanaAdapter.generate_formal_spec and core.solana_agents.KaniHarnessWriter.

The LLM is always mocked (KaniHarnessWriter._query_llm is patched); no network
calls are made and no Kani installation is needed.
"""

import os
import sys
import unittest
from unittest import mock

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.adapters.solana_adapter import SolanaAdapter
from core.pipeline.kani_utils import UNFILLED_MARKER, extract_logic_module
from core.solana_agents import KaniHarnessWriter, kani_property_ids, validate_kani_harness

LOGIC = """\
pub mod logic {
    pub fn deposit(balance: u64, amount: u64) -> Option<u64> {
        balance.checked_add(amount)
    }
}"""

PROGRAM_WITH_LOGIC = f"""\
use anchor_lang::prelude::*;

declare_id!("11111111111111111111111111111111");

{LOGIC}

#[program]
pub mod vault {{
    use super::*;
    pub fn deposit(ctx: Context<Deposit>, amount: u64) -> Result<()> {{
        Ok(())
    }}
}}
"""

PROGRAM_NO_LOGIC = """\
use anchor_lang::prelude::*;

declare_id!("11111111111111111111111111111111");

#[program]
pub mod vault {
    use super::*;
    pub fn deposit(ctx: Context<Deposit>, amount: u64) -> Result<()> {
        ctx.accounts.vault.balance = ctx.accounts.vault.balance.checked_add(amount).unwrap();
        Ok(())
    }
}
"""

MODEL_HARNESS = """\
pub struct Vault { pub balance: u64 }

#[cfg(kani)]
#[kani::proof]
fn sol_07_arithmetic_overflow() {
    let v = Vault { balance: kani::any() };
    let amount: u64 = kani::any();
    let r = v.balance.checked_add(amount);
    assert!(r.is_none() || r.unwrap() >= v.balance);
}
"""

REAL_HARNESS = LOGIC + """

#[cfg(kani)]
#[kani::proof]
fn sol_07_arithmetic_overflow() {
    let b: u64 = kani::any();
    let a: u64 = kani::any();
    if let Some(n) = logic::deposit(b, a) {
        assert!(n >= b);
    }
}
"""

PROPS = [{"id": "SOL-07", "name": "Arithmetic Overflow"}]


def make_adapter(llm_output=None, llm_error=None):
    """SolanaAdapter whose KaniHarnessWriter returns *llm_output* or raises *llm_error*."""
    adapter = SolanaAdapter(model_name="mock-model")
    writer = KaniHarnessWriter(model_name="mock-model", api_key="test", base_url="http://127.0.0.1:9")
    patcher = mock.patch.object(
        writer, "_query_llm",
        side_effect=llm_error if llm_error is not None else None,
        return_value=llm_output,
    )
    llm = patcher.start()
    adapter._harness_writer = writer
    return adapter, llm, patcher


class TestValidOutput(unittest.TestCase):

    def tearDown(self):
        mock.patch.stopall()

    def test_model_output_accepted(self):
        adapter, llm, _ = make_adapter(MODEL_HARNESS)
        spec = adapter.generate_formal_spec(PROGRAM_NO_LOGIC, PROPS)
        self.assertEqual(spec, MODEL_HARNESS)
        self.assertEqual(adapter.last_fidelity, "model")
        self.assertFalse(adapter.harness_writer.last_used_fallback)
        llm.assert_called_once()
        prompt = llm.call_args[0][1]
        self.assertIn("sol_07_arithmetic_overflow", prompt)
        self.assertIn("plain-struct model", prompt)

    def test_real_output_accepted_with_logic_module(self):
        adapter, llm, _ = make_adapter(REAL_HARNESS)
        spec = adapter.generate_formal_spec(PROGRAM_WITH_LOGIC, PROPS)
        self.assertEqual(spec, REAL_HARNESS)
        self.assertEqual(adapter.last_fidelity, "real")
        self.assertIn(LOGIC, llm.call_args[0][1])

    def test_property_id_spellings_and_strings(self):
        adapter, _, _ = make_adapter(MODEL_HARNESS)
        spec = adapter.generate_formal_spec(PROGRAM_NO_LOGIC, ["sol_07", {"id": "SOL-07"}, "SOL-05"])
        self.assertEqual(spec, MODEL_HARNESS)
        self.assertEqual(adapter.last_fidelity, "model")


class TestFallback(unittest.TestCase):

    def tearDown(self):
        mock.patch.stopall()

    def assert_scaffold(self, spec, ids):
        self.assertIn(UNFILLED_MARKER, spec)
        self.assertIn("#[kani::proof]", spec)
        self.assertEqual(validate_kani_harness(spec, ids), [])

    def check_rejected(self, output, program=PROGRAM_NO_LOGIC, props=PROPS):
        adapter, _, _ = make_adapter(output)
        spec = adapter.generate_formal_spec(program, props)
        ids = kani_property_ids(props)
        self.assert_scaffold(spec, ids)
        self.assertEqual(adapter.last_fidelity, "scaffold")
        self.assertTrue(adapter.harness_writer.last_used_fallback)
        self.assertTrue(adapter.harness_writer.last_errors)
        return adapter

    def test_empty_output(self):
        self.check_rejected("")

    def test_missing_kani_proof(self):
        self.check_rejected(MODEL_HARNESS.replace("#[kani::proof]", ""))

    def test_kani_proof_only_in_comment(self):
        self.check_rejected(MODEL_HARNESS.replace("#[kani::proof]", "// #[kani::proof]"))

    def test_anchor_lang_import(self):
        self.check_rejected("use anchor_lang::prelude::*;\n" + MODEL_HARNESS)

    def test_missing_harness_for_requested_property(self):
        props = PROPS + [{"id": "SOL-01"}]
        adapter = self.check_rejected(MODEL_HARNESS, props=props)
        self.assertTrue(any("SOL-01" in e for e in adapter.harness_writer.last_errors))
        self.assertIn("fn sol_01_signer_check", adapter.generate_formal_spec(PROGRAM_NO_LOGIC, props))

    def test_duplicate_harness(self):
        dup = MODEL_HARNESS + MODEL_HARNESS.split("}\n", 1)[1].replace(
            "sol_07_arithmetic_overflow", "sol_07_overflow_again")
        self.check_rejected(dup)

    def test_unrequested_property_harness(self):
        extra = MODEL_HARNESS + "\n#[cfg(kani)]\n#[kani::proof]\nfn sol_05_unchecked() { assert!(true); }\n"
        self.check_rejected(extra)

    def test_unknown_property_id_harness(self):
        extra = MODEL_HARNESS + "\n#[cfg(kani)]\n#[kani::proof]\nfn sol_99_made_up() { assert!(true); }\n"
        self.check_rejected(extra)

    def test_real_path_requires_logic_module_verbatim(self):
        self.check_rejected(MODEL_HARNESS, program=PROGRAM_WITH_LOGIC)

    def test_llm_exception_falls_back(self):
        adapter, llm, _ = make_adapter(llm_error=RuntimeError("connection refused"))
        spec = adapter.generate_formal_spec(PROGRAM_WITH_LOGIC, PROPS)
        llm.assert_called_once()
        self.assert_scaffold(spec, ["SOL-07"])
        self.assertEqual(adapter.last_fidelity, "scaffold")
        self.assertIn("LLM error", adapter.harness_writer.last_errors[0])

    def test_scaffold_has_one_harness_per_property(self):
        props = [{"id": "SOL-07"}, {"id": "SOL-01"}, {"id": "SOL-17"}]
        adapter, _, _ = make_adapter(llm_error=Exception("boom"))
        spec = adapter.generate_formal_spec(PROGRAM_NO_LOGIC, props)
        self.assert_scaffold(spec, ["SOL-07", "SOL-01", "SOL-17"])
        self.assertEqual(spec.count("#[kani::proof]"), 3)


class TestIneligible(unittest.TestCase):

    def tearDown(self):
        mock.patch.stopall()

    def test_only_unverified_surface_returns_empty(self):
        adapter, llm, _ = make_adapter(MODEL_HARNESS)
        props = [{"id": "SOL-05"}, {"id": "SOL-06"}, "SOL-10", {"id": "NOT-A-PROP"}]
        self.assertEqual(adapter.generate_formal_spec(PROGRAM_NO_LOGIC, props), "")
        self.assertEqual(adapter.generate_formal_spec(PROGRAM_NO_LOGIC, []), "")
        self.assertEqual(adapter.generate_formal_spec(PROGRAM_NO_LOGIC, None), "")
        llm.assert_not_called()
        self.assertIsNone(adapter.last_fidelity)

    def test_ineligible_filtered_from_prompt(self):
        adapter, llm, _ = make_adapter(MODEL_HARNESS)
        adapter.generate_formal_spec(PROGRAM_NO_LOGIC, [{"id": "SOL-05"}, {"id": "SOL-07"}])
        prompt = llm.call_args[0][1]
        self.assertNotIn("SOL-05", prompt)
        self.assertIn("SOL-07", prompt)


class TestFidelity(unittest.TestCase):

    def tearDown(self):
        mock.patch.stopall()

    def test_fixture_programs(self):
        self.assertIsNotNone(extract_logic_module(PROGRAM_WITH_LOGIC))
        self.assertIsNone(extract_logic_module(PROGRAM_NO_LOGIC))

    def test_fidelity_values(self):
        cases = [
            (PROGRAM_WITH_LOGIC, REAL_HARNESS, None, "real"),
            (PROGRAM_NO_LOGIC, MODEL_HARNESS, None, "model"),
            (PROGRAM_NO_LOGIC, "not rust", None, "scaffold"),
            (PROGRAM_WITH_LOGIC, None, RuntimeError("x"), "scaffold"),
        ]
        for program, output, error, expected in cases:
            with self.subTest(expected=expected, error=error):
                adapter, _, _ = make_adapter(output, error)
                adapter.generate_formal_spec(program, PROPS)
                self.assertEqual(adapter.last_fidelity, expected)

    def test_fidelity_reset_between_calls(self):
        adapter, llm, _ = make_adapter(llm_error=RuntimeError("x"))
        adapter.generate_formal_spec(PROGRAM_NO_LOGIC, PROPS)
        self.assertEqual(adapter.last_fidelity, "scaffold")
        llm.side_effect = None
        llm.return_value = MODEL_HARNESS
        adapter.generate_formal_spec(PROGRAM_NO_LOGIC, PROPS)
        self.assertEqual(adapter.last_fidelity, "model")


class TestStage(unittest.TestCase):

    def test_formal_spec_implemented(self):
        self.assertIn("formal_spec", SolanaAdapter.implemented_stages)
        self.assertNotIn("formal_spec", SolanaAdapter().describe()["missing_stages"])


if __name__ == "__main__":
    unittest.main()
