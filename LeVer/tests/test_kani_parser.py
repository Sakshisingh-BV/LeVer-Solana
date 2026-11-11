"""
Regression tests for parse_kani_output (CLAUDE.md KNOWN BUG 13).

Fixtures in tests/fixtures/kani/ follow Kani's multi-line
``Check N: ... - Status: SUCCESS|FAILURE`` format (see the README there).
"""

import os
import sys
import unittest

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.pipeline.kani_utils import parse_kani_output

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "kani")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class TestParseKaniOutput(unittest.TestCase):

    def test_success(self):
        result = parse_kani_output(_fixture("success.txt"), "", 0)
        self.assertTrue(result["success"])
        self.assertEqual(result["verified"], 2)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(
            result["passed_checks"],
            ["check_add.assertion.1", "check_add.arithmetic_overflow.1"],
        )
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["harnesses"], {"check_add": "SUCCESSFUL"})

    def test_failure(self):
        result = parse_kani_output(_fixture("failure.txt"), "", 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["verified"], 1)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["failed_checks"], ["check_withdraw.arithmetic_overflow.1"])
        failed = [c for c in result["checks"] if c["status"] == "FAILURE"][0]
        self.assertEqual(failed["harness"], "check_withdraw")
        self.assertEqual(failed["description"], "attempt to subtract with overflow")
        self.assertEqual(failed["location"], "src/lib.rs:34:5 in function check_withdraw")
        self.assertTrue(result["errors"])

    def test_multi_harness_one_failure_fails_overall(self):
        result = parse_kani_output(_fixture("multi_harness.txt"), "", 1)
        self.assertFalse(result["success"])
        self.assertEqual(
            result["harnesses"],
            {"check_signer": "SUCCESSFUL", "check_pda_bump": "FAILED"},
        )
        self.assertEqual(result["passed_checks"], ["check_signer.assertion.1"])
        self.assertEqual(result["failed_checks"], ["check_pda_bump.assertion.1"])

    def test_multi_harness_failure_not_masked_by_exit_zero(self):
        # Even if the exit code were 0, a FAILED harness must not count as success.
        self.assertFalse(parse_kani_output(_fixture("multi_harness.txt"), "", 0)["success"])

    def test_undetermined_is_not_success(self):
        result = parse_kani_output(_fixture("undetermined.txt"), "", 0)
        self.assertFalse(result["success"])
        self.assertEqual(result["undetermined_checks"], ["check_loop.assertion.1"])
        self.assertEqual(result["failed_checks"], ["check_loop.unwind.0"])

    def test_empty_output(self):
        result = parse_kani_output("", "error: no such command: `kani`", 101)
        self.assertFalse(result["success"])
        self.assertEqual(result["checks"], [])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
