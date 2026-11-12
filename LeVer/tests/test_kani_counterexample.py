"""
Tests for extract_kani_counterexample and parse_kani_output's ``counterexamples``.

All inputs are real ``cargo kani`` 0.68.0 / CBMC 6.11.0 output recorded in
tests/fixtures/kani/recorded/.
"""

import os
import sys
import unittest

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.pipeline.kani_utils import (
    UNFILLED_MARKER,
    extract_kani_counterexample,
    parse_kani_output,
)

RECORDED = os.path.join(os.path.dirname(__file__), "fixtures", "kani", "recorded")

KEYS = {
    "source", "harness", "property_id", "check",
    "description", "location", "assignments", "raw_trace",
}


def _recorded(name):
    with open(os.path.join(RECORDED, name), encoding="utf-8") as f:
        return f.read()


class TestExtractKaniCounterexample(unittest.TestCase):

    def test_failure_with_concrete_playback(self):
        cex = extract_kani_counterexample(_recorded("failure_playback.txt"))
        self.assertIsNotNone(cex)
        self.assertEqual(set(cex), KEYS)
        self.assertEqual(cex["source"], "kani")
        self.assertEqual(cex["harness"], "sol_07_unchecked_overflow")
        self.assertEqual(cex["property_id"], "SOL-07")
        self.assertEqual(cex["check"], "add_unchecked.assertion.1")
        self.assertEqual(cex["description"], "attempt to add with overflow")
        self.assertEqual(cex["location"], "src/lib.rs:1:47")
        self.assertEqual(
            cex["assignments"],
            {"input_0": "9223372036854775808", "input_1": "9223372036854775808"},
        )
        self.assertIn("Check 1: add_unchecked.assertion.1", cex["raw_trace"])
        self.assertIn("Concrete playback unit test for `sol_07_unchecked_overflow`", cex["raw_trace"])
        self.assertIn("vec![0, 0, 0, 0, 0, 0, 0, 128]", cex["raw_trace"])

    def test_unfilled_scaffold_strips_doubled_quotes(self):
        text = _recorded("unfilled.txt")
        # The recorded output really does double the quotes around assert messages.
        self.assertIn('""LEVER_UNFILLED_HARNESS: SOL-07 harness not filled in""', text)

        cex = extract_kani_counterexample(text)
        self.assertIsNotNone(cex)
        self.assertEqual(cex["harness"], "sol_07_arithmetic_overflow")
        self.assertEqual(cex["property_id"], "SOL-07")
        self.assertEqual(cex["check"], "sol_07_arithmetic_overflow.assertion.1")
        self.assertEqual(
            cex["description"],
            "LEVER_UNFILLED_HARNESS: SOL-07 harness not filled in",
        )
        self.assertFalse(cex["description"].startswith('"'))
        self.assertFalse(cex["description"].endswith('"'))
        self.assertIn(UNFILLED_MARKER, cex["description"])
        self.assertEqual(cex["location"], "src/lib.rs:10:5")
        # No concrete playback block in this run.
        self.assertEqual(cex["assignments"], {})

    def test_success_returns_none(self):
        self.assertIsNone(extract_kani_counterexample(_recorded("success.txt")))

    def test_multi_harness_reports_first_failing_harness(self):
        cex = extract_kani_counterexample(_recorded("multi_harness.txt"))
        self.assertIsNotNone(cex)
        self.assertEqual(cex["harness"], "sol_07_unchecked_overflow")
        self.assertEqual(cex["property_id"], "SOL-07")
        self.assertEqual(cex["check"], "add_unchecked.assertion.1")
        self.assertEqual(cex["description"], "attempt to add with overflow")
        self.assertEqual(cex["location"], "src/lib.rs:1:47")
        self.assertEqual(cex["assignments"], {})

    def test_empty_input_returns_none(self):
        self.assertIsNone(extract_kani_counterexample(""))

    def test_crlf_output(self):
        cex = extract_kani_counterexample(_recorded("failure_playback.txt").replace("\n", "\r\n"))
        self.assertEqual(
            cex["assignments"],
            {"input_0": "9223372036854775808", "input_1": "9223372036854775808"},
        )


class TestParseKaniOutputCounterexamples(unittest.TestCase):

    def test_failure_playback(self):
        text = _recorded("failure_playback.txt")
        result = parse_kani_output(text, "", 1)
        self.assertEqual(result["counterexamples"], [extract_kani_counterexample(text)])

    def test_success_has_none(self):
        result = parse_kani_output(_recorded("success.txt"), "", 0)
        self.assertEqual(result["counterexamples"], [])

    def test_success_counts_check_names_with_spaces(self):
        result = parse_kani_output(_recorded("success.txt"), "", 0)
        self.assertTrue(result["success"])
        self.assertEqual(result["verified"], 3)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(
            result["passed_checks"],
            [
                "core::num::<impl u64>::checked_add.arithmetic_overflow.1",
                "sol_07_checked_ok.unreachable.1",
                "sol_07_checked_ok.assertion.1",
            ],
        )

    def test_failure_in_check_name_with_spaces_detected(self):
        text = (
            "Checking harness sol_07_overflow...\n"
            "\n"
            "RESULTS:\n"
            "Check 1: core::num::<impl u64>::checked_add.arithmetic_overflow.1\n"
            "         - Status: FAILURE\n"
            "         - Description: \"attempt to compute `unchecked_add` which would overflow\"\n"
            "         - Location: library/core/src/num/uint_macros.rs:942:31 in function core::num::<impl u64>::checked_add\n"
            "\n"
            "Check 2: sol_07_overflow.assertion.1\n"
            "         - Status: SUCCESS\n"
            "         - Description: \"assertion failed: s >= a\"\n"
            "         - Location: src/lib.rs:8:5 in function sol_07_overflow\n"
            "\n"
            "SUMMARY:\n"
            " ** 1 of 2 failed\n"
            "\n"
            "VERIFICATION:- FAILED\n"
        )
        name = "core::num::<impl u64>::checked_add.arithmetic_overflow.1"
        # Exit code 0 on purpose: the failure must be caught from the check itself too.
        result = parse_kani_output(text, "", 0)
        self.assertFalse(result["success"])
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["failed_checks"], [name])
        self.assertEqual(result["passed_checks"], ["sol_07_overflow.assertion.1"])
        failed = [c for c in result["checks"] if c["status"] == "FAILURE"][0]
        self.assertEqual(failed["harness"], "sol_07_overflow")
        self.assertEqual(
            failed["description"], "attempt to compute `unchecked_add` which would overflow"
        )

        cex = extract_kani_counterexample(text)
        self.assertIsNotNone(cex)
        self.assertEqual(cex["harness"], "sol_07_overflow")
        self.assertEqual(cex["check"], name)

        # CRLF output is handled the same way.
        crlf = parse_kani_output(text.replace("\n", "\r\n"), "", 1)
        self.assertEqual(crlf["failed_checks"], [name])

    def test_multi_harness_one_entry_per_failed_harness(self):
        result = parse_kani_output(_recorded("multi_harness.txt"), "", 1)
        self.assertEqual(
            result["harnesses"],
            {"sol_07_unchecked_overflow": "FAILED", "sol_07_checked_ok": "SUCCESSFUL"},
        )
        self.assertEqual(
            [c["harness"] for c in result["counterexamples"]],
            ["sol_07_unchecked_overflow"],
        )

    def test_unfilled_check_description_unquoted(self):
        result = parse_kani_output(_recorded("unfilled.txt"), "", 1)
        failed = [c for c in result["checks"] if c["status"] == "FAILURE"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(
            failed[0]["description"],
            "LEVER_UNFILLED_HARNESS: SOL-07 harness not filled in",
        )
        self.assertEqual(len(result["counterexamples"]), 1)


if __name__ == "__main__":
    unittest.main()
