"""Tests for core.solana_property_selector (no LLM, no Kani)."""
import os
import unittest
from unittest import mock

from core.solana_property_selector import BASELINE, select_solana_kani_properties

VAULT = '''
use anchor_lang::prelude::*;
#[program]
pub mod vault {
    use super::*;
    pub fn withdraw(ctx: Context<Withdraw>, amount: u64) -> Result<()> {
        let rent = Rent::get()?;
        **ctx.accounts.vault.to_account_info().try_borrow_mut_lamports()? -= amount;
        Ok(())
    }
}
#[derive(Accounts)]
pub struct Init<'info> {
    #[account(
        init,
        payer = owner,
        space = 8 + 41,
        seeds = [b"vault", owner.key().as_ref()],
        bump
    )]
    pub vault: Account<'info, Vault>,
    #[account(mut)]
    pub owner: Signer<'info>,
}
'''

PLAIN = '''
use anchor_lang::prelude::*;
#[program]
pub mod counter {
    use super::*;
    // seeds = [b"x"] and realloc only in a comment
    pub fn bump_count(ctx: Context<Bump>) -> Result<()> {
        let note = "init_if_needed remaining_accounts";
        ctx.accounts.counter.count = ctx.accounts.counter.count.checked_add(1).unwrap();
        Ok(())
    }
}
#[derive(Accounts)]
pub struct Bump<'info> {
    #[account(mut)]
    pub counter: Account<'info, Counter>,
    pub authority: Signer<'info>,
}
'''


class TestSelector(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("LEVER_SOLANA_KANI_PROPERTIES", None)
        os.environ.pop("LEVER_SOLANA_PROPERTY_SELECTION", None)

    def test_baseline_always_kept(self):
        ids, reasons = select_solana_kani_properties(PLAIN)
        self.assertEqual(ids, sorted(BASELINE))
        self.assertEqual(reasons, {})

    def test_comments_and_strings_do_not_trigger(self):
        ids, _ = select_solana_kani_properties(PLAIN)
        for pid in ("SOL-03", "SOL-12", "SOL-16", "SOL-18"):
            self.assertNotIn(pid, ids)

    def test_vault_adds_pda_init_and_lamports(self):
        ids, reasons = select_solana_kani_properties(VAULT)
        for pid in ("SOL-03", "SOL-12", "SOL-17"):
            self.assertIn(pid, ids)
            self.assertIn(pid, reasons)
        self.assertEqual(ids, sorted(ids))
        for pid in BASELINE:
            self.assertIn(pid, ids)

    def test_unverified_surface_never_selected(self):
        code = VAULT + "\nlet ix = invoke_signed(&ix, &accts, &[seeds]); // CPI\n"
        ids, _ = select_solana_kani_properties(code)
        for pid in ("SOL-05", "SOL-06", "SOL-10", "SOL-14", "SOL-15"):
            self.assertNotIn(pid, ids)

    def test_selection_can_be_switched_off(self):
        os.environ["LEVER_SOLANA_PROPERTY_SELECTION"] = "0"
        ids, _ = select_solana_kani_properties(VAULT)
        self.assertEqual(ids, sorted(BASELINE))

    def test_pinned_list_wins_and_drops_ineligible(self):
        os.environ["LEVER_SOLANA_KANI_PROPERTIES"] = "SOL-03, sol-01, SOL-05"
        ids, _ = select_solana_kani_properties(PLAIN)
        self.assertEqual(ids, ["SOL-01", "SOL-03"])


if __name__ == "__main__":
    unittest.main()
