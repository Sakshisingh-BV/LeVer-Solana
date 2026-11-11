"""
Tests for the Kani harness helpers: core/kani_templates.py and the scaffold /
logic-module / crate / harness-name helpers in core/pipeline/kani_utils.py.

No Kani installation is needed; nothing here runs cargo.
"""

import os
import re
import sys
import tempfile
import unittest

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.kani_templates import (
    DEFAULT_UNWIND,
    KANI_ELIGIBLE,
    UNVERIFIED_SURFACE,
    get_kani_template,
    kani_templates,
    normalize_property_id,
)
from core.pipeline.kani_utils import (
    UNFILLED_MARKER,
    extract_logic_module,
    generate_kani_harness_scaffold,
    harness_property_id,
    write_kani_crate,
)

ANCHOR_PROGRAM = """\
use anchor_lang::prelude::*;

declare_id!("11111111111111111111111111111111");

#[program]
pub mod lever_target {
    use super::*;

    pub fn initialize(ctx: Context<Initialize>, amount: u64) -> Result<()> {
        ctx.accounts.vault.balance = logic::deposit(0, amount).ok_or(ErrorCode::Overflow)?;
        Ok(())
    }

    pub fn withdraw<'info>(ctx: Context<Withdraw<'info>>, amount: u64) -> Result<()> {
        Ok(())
    }
}
"""

CLEAN_LOGIC = """\
// anchor_lang is not used in here, and this comment has a stray } brace
pub mod logic {
    use std::cmp::min;

    pub const OPEN_BRACE: char = '{';
    pub const NOTE: &str = "require!(x) and super::thing } are just text";

    pub struct Vault<'a> { pub name: &'a str, pub balance: u64 }

    #[derive(Debug, PartialEq)]
    pub enum LogicError { Overflow }

    pub fn deposit(balance: u64, amount: u64) -> Option<u64> {
        balance.checked_add(amount)
    }

    pub fn withdraw(balance: u64, amount: u64) -> Result<u64, LogicError> {
        if amount > balance { return Err(LogicError::Overflow); }
        Ok(balance - min(amount, balance))
    }
}"""


class TestKaniTemplates(unittest.TestCase):

    def test_split_covers_catalogue_without_overlap(self):
        self.assertEqual(set(KANI_ELIGIBLE) & set(UNVERIFIED_SURFACE), set())
        self.assertEqual(
            set(KANI_ELIGIBLE) | set(UNVERIFIED_SURFACE),
            {f"SOL-{i:02d}" for i in range(1, 19)},
        )

    def test_every_eligible_property_has_a_template(self):
        templates = kani_templates()
        self.assertEqual(set(templates), set(KANI_ELIGIBLE))
        names = [t.harness_name for t in templates.values()]
        self.assertEqual(len(names), len(set(names)))
        for pid, t in templates.items():
            num = pid.split("-")[1]
            self.assertEqual(t.harness_prefix, f"sol_{num}_")
            self.assertTrue(t.harness_name.startswith(t.harness_prefix))
            self.assertRegex(t.harness_name, r"^[a-z][a-z0-9_]*$")
            self.assertTrue(t.prompt_snippet.startswith("Invariant: "))

    def test_snippet_uses_formal_invariant_when_present(self):
        self.assertEqual(get_kani_template("SOL-12").snippet_source, "formal_invariant")
        self.assertIn("Uninitialized", get_kani_template("SOL-12").prompt_snippet)
        self.assertIn("Kani scope:", get_kani_template("SOL-17").prompt_snippet)
        # SOL-01..09 have no formal_invariant in the catalogue yet.
        self.assertEqual(get_kani_template("SOL-07").snippet_source, "invariant_template")

    def test_unverified_surface_has_no_template(self):
        for pid in UNVERIFIED_SURFACE:
            self.assertIsNone(get_kani_template(pid))

    def test_normalize_property_id(self):
        for value in ("SOL-07", "sol_07", "SOL_07_overflow", "sol-7", " Sol 07"):
            self.assertEqual(normalize_property_id(value), "SOL-07", value)
        for value in ("SOL-99", "SOL-070", "check_add", "", None, 7):
            self.assertIsNone(normalize_property_id(value), value)


class TestHarnessScaffold(unittest.TestCase):

    def test_scaffold_has_proof_attribute_and_harness_name(self):
        src = generate_kani_harness_scaffold(ANCHOR_PROGRAM, "SOL-07", "")
        self.assertIn("#[cfg(kani)]", src)
        self.assertIn("#[kani::proof]", src)
        self.assertIn(f"#[kani::unwind({DEFAULT_UNWIND})]", src)
        self.assertIn("fn sol_07_arithmetic_overflow() {", src)
        self.assertIn("Candidate instruction handlers: initialize, withdraw", src)

    def test_every_eligible_property_scaffolds_to_its_own_name(self):
        for pid in KANI_ELIGIBLE:
            src = generate_kani_harness_scaffold("", pid, "")
            fns = re.findall(r"^fn (\w+)\(\)", src, re.MULTILINE)
            self.assertEqual(fns, [get_kani_template(pid).harness_name], pid)
            self.assertEqual(harness_property_id(fns[0]), pid)

    def test_scaffold_is_fail_closed(self):
        src = generate_kani_harness_scaffold(ANCHOR_PROGRAM, "SOL-12", "")
        body = src[src.index("fn sol_12_"):]
        # The only statement is an assertion that can never hold.
        self.assertIn(f'assert!(false, "{UNFILLED_MARKER}: SOL-12', body)
        self.assertNotIn("kani::assume", body)
        self.assertNotIn("kani::any", body)

    def test_alternative_id_spellings(self):
        for name in ("sol_01", "SOL_01_signer_check", "sol-1"):
            self.assertIn("fn sol_01_signer_check()", generate_kani_harness_scaffold("", name, ""))

    def test_description_is_commented_and_defaults_to_snippet(self):
        src = generate_kani_harness_scaffold("", "SOL-04", 'line one\nline "two"')
        self.assertIn("// line one\n// line \"two\"\n", src)
        default = generate_kani_harness_scaffold("", "SOL-04", "  ")
        self.assertIn("// Invariant: ", default)
        for line in src.splitlines():
            self.assertTrue(
                line.startswith(("//", "#[", "fn ", "    assert!", "}")), line
            )

    def test_unknown_or_ineligible_ids_produce_no_harness(self):
        for name in ("SOL-05", "SOL-06", "SOL-10", "SOL-14", "SOL-15",
                     "SOL-99", "SOL-00", "check_add", "", "signer"):
            with self.assertRaises(ValueError, msg=name):
                generate_kani_harness_scaffold(ANCHOR_PROGRAM, name, "some description")


class TestExtractLogicModule(unittest.TestCase):

    def test_accepts_dependency_free_module(self):
        code = ANCHOR_PROGRAM + "\n" + CLEAN_LOGIC + "\n\n#[error_code]\npub enum ErrorCode { Overflow }\n"
        module = extract_logic_module(code)
        self.assertEqual(module, CLEAN_LOGIC[CLEAN_LOGIC.index("pub mod logic"):])

    def test_accepts_pub_crate_module(self):
        code = "pub(crate) mod logic { pub fn add(a: u8, b: u8) -> u8 { a.wrapping_add(b) } }"
        self.assertEqual(extract_logic_module(code), code)

    def test_rejects_modules_tied_to_anchor_or_outer_scope(self):
        bad_bodies = [
            "use super::*; pub fn f() {}",
            "use anchor_lang::prelude::*; pub fn f() {}",
            "pub fn f(ctx: Context<Init>) {}",
            "pub fn f(a: u64) -> Result<u64> { Ok(a) }",
            "pub fn f(a: u64) { require!(a > 0, E::Bad); }",
            "pub fn f(k: Pubkey) {}",
            "pub fn f() { crate::other(); }",
            "use num_traits::CheckedAdd; pub fn f() {}",
            "pub fn f() { msg!(\"hi\"); }",
            "#[account] pub struct S { a: u64 }",
        ]
        for body in bad_bodies:
            self.assertIsNone(extract_logic_module(f"pub mod logic {{ {body} }}"), body)

    def test_none_without_inline_logic_module(self):
        self.assertIsNone(extract_logic_module(ANCHOR_PROGRAM))
        self.assertIsNone(extract_logic_module("pub mod logic;"))
        self.assertIsNone(extract_logic_module("mod logic { pub fn f() {} }"))  # private
        self.assertIsNone(extract_logic_module("// pub mod logic { }"))
        self.assertIsNone(extract_logic_module(""))

    def test_none_on_unbalanced_braces(self):
        self.assertIsNone(extract_logic_module("pub mod logic { pub fn f() { "))


class TestWriteKaniCrate(unittest.TestCase):

    def test_writes_standalone_crate(self):
        with tempfile.TemporaryDirectory() as tmp:
            crate = os.path.join(tmp, "kani_workspace")
            path = write_kani_crate(crate, "pub fn f() {}")
            self.assertEqual(path, os.path.abspath(crate))
            with open(os.path.join(crate, "Cargo.toml"), encoding="utf-8") as f:
                toml = f.read()
            with open(os.path.join(crate, "src", "lib.rs"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "pub fn f() {}\n")
        self.assertIn("[workspace]", toml)
        deps = toml.split("[dependencies]", 1)[1].split("\n[", 1)[0]
        self.assertEqual([l for l in deps.splitlines() if l and not l.startswith("#")], [])
        self.assertNotIn("anchor", toml.replace("anchor-lang / solana-program", ""))

    def test_overwrites_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_kani_crate(tmp, "pub fn old() {}")
            write_kani_crate(tmp, "pub fn new() {}\n")
            with open(os.path.join(tmp, "src", "lib.rs"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "pub fn new() {}\n")

    def test_rejects_empty_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            for src in ("", "   \n"):
                with self.assertRaises(ValueError):
                    write_kani_crate(tmp, src)
            self.assertFalse(os.path.exists(os.path.join(tmp, "Cargo.toml")))


class TestHarnessPropertyId(unittest.TestCase):

    def test_maps_convention_names(self):
        cases = {
            "sol_07_arithmetic_overflow": "SOL-07",
            "sol_01_signer_check": "SOL-01",
            "sol_17_lamport_conservation_vault": "SOL-17",
            "proofs::sol_12_reinitialization": "SOL-12",
            "lever_kani::proofs::sol_04_duplicate_accounts": "SOL-04",
            "sol_18": "SOL-18",
        }
        for name, pid in cases.items():
            self.assertEqual(harness_property_id(name), pid, name)

    def test_rejects_other_names(self):
        for name in ("check_add", "check_signer", "sol_7_overflow", "sol_070_x",
                     "SOL_07_overflow", "my_sol_07_x", "", None):
            self.assertIsNone(harness_property_id(name), name)

    def test_ineligible_properties_are_never_attributed(self):
        for pid in UNVERIFIED_SURFACE:
            self.assertIsNone(harness_property_id(f"sol_{pid[-2:]}_anything"), pid)
        self.assertIsNone(harness_property_id("sol_99_x"))


if __name__ == "__main__":
    unittest.main()
