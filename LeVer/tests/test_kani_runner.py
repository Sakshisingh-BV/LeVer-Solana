"""Tests for SolanaAdapter.verify_spec / extract_counterexample (the ``cargo kani`` runner).

subprocess.run is mocked; its output is real ``cargo kani`` 0.68.0 output recorded in
tests/fixtures/kani/recorded/. No cargo or Kani install is needed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.adapters import solana_adapter
from core.adapters.solana_adapter import SolanaAdapter, kani_command
from core.pipeline.kani_utils import parse_kani_output

RECORDED = os.path.join(os.path.dirname(__file__), "fixtures", "kani", "recorded")

SPEC = "#[cfg(kani)]\n#[kani::proof]\nfn sol_07_checked_ok() {}\n"
FLAGS = ["--output-format", "regular", "-Z", "concrete-playback", "--concrete-playback=print"]
EMPTY_PARSE = {
    "success": False,
    "verified": 0,
    "failed": 0,
    "passed_checks": [],
    "failed_checks": [],
    "undetermined_checks": [],
    "checks": [],
    "harnesses": {},
    "counterexamples": [],
}


def _recorded(name):
    with open(os.path.join(RECORDED, name), encoding="utf-8") as f:
        return f.read()


def _completed(stdout, returncode):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


class KaniRunnerTestCase(unittest.TestCase):

    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="lever_kani_test_")
        self.addCleanup(shutil.rmtree, self.workspace, ignore_errors=True)
        self.crate_dir = os.path.join(self.workspace, "kani_workspace")
        self.adapter = SolanaAdapter(model_name="test-model")
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("KANI_TIMEOUT", None)
        cli = mock.patch("core.solana_config.CARGO_KANI_CLI", "cargo-kani")
        cli.start()
        self.addCleanup(cli.stop)

    def _run(self, **run_kwargs):
        with mock.patch.object(solana_adapter.subprocess, "run", **run_kwargs) as run:
            result = self.adapter.verify_spec(SPEC, self.workspace)
        return result, run

    def _result_json(self):
        with open(os.path.join(self.crate_dir, "kani_result.json"), encoding="utf-8") as f:
            return json.load(f)

    def _assert_invocation(self, run, timeout=300):
        run.assert_called_once()
        args, kwargs = run.call_args
        cmd = args[0]
        self.assertEqual(cmd, ["cargo-kani", "kani"] + FLAGS)
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "regular")
        self.assertIn("-Z", cmd)
        self.assertEqual(cmd[cmd.index("-Z") + 1], "concrete-playback")
        self.assertIn("--concrete-playback=print", cmd)
        self.assertEqual(kwargs["cwd"], os.path.abspath(self.crate_dir))
        self.assertEqual(kwargs["timeout"], timeout)
        self.assertTrue(kwargs["capture_output"])
        self.assertTrue(kwargs["text"])


class TestVerifySpec(KaniRunnerTestCase):

    def test_success(self):
        out = _recorded("success.txt")
        result, run = self._run(return_value=_completed(out, 0))

        self.assertEqual(result, (True, []))
        self._assert_invocation(run)
        with open(os.path.join(self.crate_dir, "src", "lib.rs"), encoding="utf-8") as f:
            self.assertEqual(f.read(), SPEC)
        self.assertTrue(os.path.isfile(os.path.join(self.crate_dir, "Cargo.toml")))

        expected = parse_kani_output(out, "", 0)
        expected.update({
            "infra_error": False,
            "fidelity": "unknown",
            "properties": {
                "SOL-07": {"status": "SUCCESSFUL", "harnesses": {"sol_07_checked_ok": "SUCCESSFUL"}},
            },
            "command": ["cargo-kani", "kani"] + FLAGS,
        })
        data = self._result_json()
        self.assertEqual(data, expected)
        self.assertTrue(data["success"])
        self.assertEqual(data["failed"], 0)
        self.assertEqual(data["harnesses"], {"sol_07_checked_ok": "SUCCESSFUL"})
        self.assertEqual(self.adapter.last_kani_result, data)

    def test_failure_with_playback(self):
        out = _recorded("failure_playback.txt")
        self.adapter.last_fidelity = "hybrid"
        result, run = self._run(return_value=_completed(out, 1))

        self.assertEqual(result, (False, [
            "SOL-07 sol_07_unchecked_overflow: attempt to add with overflow"
            " @ src/lib.rs:1:47 in function add_unchecked",
        ]))
        self._assert_invocation(run)

        expected = parse_kani_output(out, "", 1)
        expected.update({
            "infra_error": False,
            "fidelity": "hybrid",
            "properties": {
                "SOL-07": {"status": "FAILED", "harnesses": {"sol_07_unchecked_overflow": "FAILED"}},
            },
            "command": ["cargo-kani", "kani"] + FLAGS,
        })
        data = self._result_json()
        self.assertEqual(data, expected)
        self.assertFalse(data["success"])
        self.assertFalse(data["infra_error"])
        self.assertEqual(data["failed_checks"], ["add_unchecked.assertion.1"])
        self.assertEqual(len(data["counterexamples"]), 1)
        cex = data["counterexamples"][0]
        self.assertEqual(cex["property_id"], "SOL-07")
        self.assertEqual(cex["assignments"], {
            "input_0": "9223372036854775808",
            "input_1": "9223372036854775808",
        })
        self.assertEqual(self.adapter.last_kani_result, data)

    def test_multi_harness_property_map(self):
        out = _recorded("multi_harness.txt")
        result, _ = self._run(return_value=_completed(out, 1))
        self.assertEqual(result, (False, [
            "SOL-07 sol_07_unchecked_overflow: attempt to add with overflow"
            " @ src/lib.rs:1:47 in function add_unchecked",
        ]))
        self.assertEqual(self._result_json()["properties"], {
            "SOL-07": {
                "status": "FAILED",
                "harnesses": {
                    "sol_07_unchecked_overflow": "FAILED",
                    "sol_07_checked_ok": "SUCCESSFUL",
                },
            },
        })

    def test_timeout(self):
        result, run = self._run(side_effect=subprocess.TimeoutExpired(cmd="cargo-kani", timeout=300))

        self.assertEqual(result, (False, ["infra_error: kani timeout after 300s"]))
        self._assert_invocation(run)
        expected = dict(EMPTY_PARSE)
        expected.update({
            "errors": ["infra_error: kani timeout after 300s"],
            "infra_error": True,
            "fidelity": "unknown",
            "properties": {},
            "command": ["cargo-kani", "kani"] + FLAGS,
        })
        self.assertEqual(self._result_json(), expected)
        self.assertEqual(self.adapter.last_kani_result, expected)

    def test_missing_tool(self):
        result, run = self._run(side_effect=FileNotFoundError(2, "No such file", "cargo-kani"))

        self.assertEqual(result, (False, ["infra_error: cargo-kani not found"]))
        self._assert_invocation(run)
        expected = dict(EMPTY_PARSE)
        expected.update({
            "errors": ["infra_error: cargo-kani not found"],
            "infra_error": True,
            "fidelity": "unknown",
            "properties": {},
            "command": ["cargo-kani", "kani"] + FLAGS,
        })
        self.assertEqual(self._result_json(), expected)
        self.assertEqual(self.adapter.last_kani_result, expected)

    def test_timeout_env_override(self):
        os.environ["KANI_TIMEOUT"] = "45"
        result, run = self._run(side_effect=subprocess.TimeoutExpired(cmd="cargo-kani", timeout=45))
        self.assertEqual(result, (False, ["infra_error: kani timeout after 45s"]))
        self.assertEqual(run.call_args.kwargs["timeout"], 45)

    def test_timeout_kwarg_overrides_env(self):
        os.environ["KANI_TIMEOUT"] = "45"
        with mock.patch.object(solana_adapter.subprocess, "run",
                               return_value=_completed(_recorded("success.txt"), 0)) as run:
            self.assertEqual(self.adapter.verify_spec(SPEC, self.workspace, timeout=10), (True, []))
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    def test_no_parsed_failure_is_not_success(self):
        result, _ = self._run(return_value=_completed("error[E0425]: cannot find value `x`\n", 101))
        self.assertEqual(result, (False, [
            "kani: verification did not succeed (exit code 101, no failing check parsed)",
        ]))
        self.assertFalse(self._result_json()["infra_error"])


class TestKaniCommand(unittest.TestCase):

    def test_plugin_binary_gets_subcommand(self):
        self.assertEqual(kani_command("cargo-kani"), ["cargo-kani", "kani"])
        self.assertEqual(kani_command("cargo-kani.exe"), ["cargo-kani.exe", "kani"])

    def test_cargo_subcommand_form(self):
        self.assertEqual(kani_command("cargo kani"), ["cargo", "kani"])

    def test_cargo_routed_command_uses_configured_cli(self):
        with mock.patch("core.solana_config.CARGO_KANI_CLI", "cargo kani"), \
                tempfile.TemporaryDirectory() as ws, \
                mock.patch.object(solana_adapter.subprocess, "run",
                                  return_value=_completed(_recorded("success.txt"), 0)) as run:
            SolanaAdapter().verify_spec(SPEC, ws)
        self.assertEqual(run.call_args.args[0], ["cargo", "kani"] + FLAGS)


class TestExtractCounterexample(unittest.TestCase):

    def test_failure(self):
        cex = SolanaAdapter().extract_counterexample(_recorded("failure_playback.txt"))
        self.assertEqual(cex["harness"], "sol_07_unchecked_overflow")
        self.assertEqual(cex["property_id"], "SOL-07")
        self.assertEqual(cex["description"], "attempt to add with overflow")
        self.assertEqual(cex["location"], "src/lib.rs:1:47")
        self.assertEqual(cex["assignments"], {
            "input_0": "9223372036854775808",
            "input_1": "9223372036854775808",
        })

    def test_success_has_none(self):
        self.assertIsNone(SolanaAdapter().extract_counterexample(_recorded("success.txt")))
        self.assertIsNone(SolanaAdapter().extract_counterexample(""))


class TestStages(unittest.TestCase):

    def test_formal_spec_verify_and_counterexample_implemented(self):
        stages = SolanaAdapter.implemented_stages
        self.assertIn("formal_spec", stages)
        self.assertIn("verify", stages)
        self.assertIn("counterexample", stages)
        self.assertNotIn("counterexample", SolanaAdapter().describe()["missing_stages"])


if __name__ == "__main__":
    unittest.main()
