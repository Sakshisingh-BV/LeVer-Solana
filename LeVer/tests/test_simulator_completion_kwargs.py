"""
Tests for SimulationRunner._llm_completion_kwargs: temperature is only sent when
LLM_TEMPERATURE is set. The client is mocked; no network calls are made and
SimulationRunner.__init__ (which sets up the simulation environment) is skipped.
"""

import os
import sys
import unittest
from unittest import mock

LEVER_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if LEVER_ROOT not in sys.path:
    sys.path.insert(0, LEVER_ROOT)

from core.simulator import SimulationRunner


class SimulatorCompletionKwargsTest(unittest.TestCase):
    def _sent_kwargs(self, model_name, env):
        with mock.patch.dict(os.environ, env, clear=False):
            if "LLM_TEMPERATURE" not in env:
                os.environ.pop("LLM_TEMPERATURE", None)
            runner = SimulationRunner.__new__(SimulationRunner)
            runner.client = mock.MagicMock()
            runner.client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": "hi"}],
                **runner._llm_completion_kwargs(model_name),
            )
            create = runner.client.chat.completions.create
            create.assert_called_once()
            return create.call_args.kwargs

    def test_temperature_absent_by_default(self):
        kwargs = self._sent_kwargs("claude-opus-5-5", {})
        self.assertNotIn("temperature", kwargs)
        self.assertIn("max_tokens", kwargs)

    def test_temperature_absent_when_env_empty(self):
        kwargs = self._sent_kwargs("claude-opus-5-5", {"LLM_TEMPERATURE": "  "})
        self.assertNotIn("temperature", kwargs)

    def test_temperature_present_when_env_set(self):
        kwargs = self._sent_kwargs("claude-opus-5-5", {"LLM_TEMPERATURE": "0.2"})
        self.assertEqual(kwargs["temperature"], 0.2)

    def test_gpt5_never_gets_temperature(self):
        kwargs = self._sent_kwargs("gpt-5-mini", {"LLM_TEMPERATURE": "0.2"})
        self.assertNotIn("temperature", kwargs)
        self.assertIn("max_completion_tokens", kwargs)


if __name__ == "__main__":
    unittest.main()
