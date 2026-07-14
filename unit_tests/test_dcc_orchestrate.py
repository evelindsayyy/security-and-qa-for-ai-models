"""
Unit tests for evaluator/dcc_orchestrate.py — the self-serve DCC chain.

Fully offline: hf_intake.validate, the scripts.dcc.vllm cmd_* helpers, and the
runner subprocess are all mocked, so no Hugging Face calls, no Slurm, no GPU.
The tests pin the orchestration CONTRACT:

  * chain order            validate -> start -> wait -> runner -> stop
  * teardown-always         once a job is submitted, stop runs on every failure
  * no-teardown-before-start validate/start failures never scancel a job
  * endpoint handoff        the vLLM node:port reaches the runner
  * per-run state isolation two runs use two different .jobs/<slug>.env files
  * dry run                 side-effect-free preview of the whole chain

Run from repo root:
  uv run python -m unittest unit_tests.test_dcc_orchestrate -v
"""

from __future__ import annotations

import contextlib
import unittest
from unittest import mock

from evaluator import dcc_orchestrate as orch
from evaluator import hf_intake

_GOOD = hf_intake.ValidationResult(
    True, None,
    hf_intake.ModelInfo(
        repo_id="Qwen/Qwen2.5-7B-Instruct",
        architectures=["Qwen2ForCausalLM"],
        num_params=7_000_000_000, gated=False,
    ),
)
_BAD = hf_intake.ValidationResult(False, "model is gated/private; not supported in the MVP")

_STATE = {"HOST": "node23", "PORT": "8000", "JOB_ID": "12345",
          "MODEL": "Qwen/Qwen2.5-7B-Instruct"}

_REPO = "Qwen/Qwen2.5-7B-Instruct"
_JUDGE = "Llama 4 Maverick"


@contextlib.contextmanager
def _patched(calls, *, validation=_GOOD, start_rc=0, wait_rc=0, runner_rc=0,
             runner_exc=None, start_exc=None, wait_exc=None, read_state=None):
    """Patch the whole chain; append a label to `calls` as each stage runs."""
    def _validate(_repo):
        calls.append("validate")
        return validation

    def _start(_args):
        calls.append("start")
        if start_exc:
            raise start_exc
        return start_rc

    def _wait(_args):
        calls.append("wait")
        if wait_exc:
            raise wait_exc
        return wait_rc

    def _stop(_args):
        calls.append("stop")
        return 0

    def _runner(*_a, **_k):
        calls.append("runner")
        if runner_exc:
            raise runner_exc
        return runner_rc

    with mock.patch.object(orch.hf_intake, "validate", side_effect=_validate), \
         mock.patch.object(orch.vllm, "cmd_start", side_effect=_start), \
         mock.patch.object(orch.vllm, "cmd_wait", side_effect=_wait), \
         mock.patch.object(orch.vllm, "cmd_stop", side_effect=_stop), \
         mock.patch.object(orch.vllm, "_read_state", return_value=(read_state or _STATE)), \
         mock.patch.object(orch, "_invoke_runner", side_effect=_runner) as runner_mock:
        yield runner_mock


class OrchestrateHappyPathTest(unittest.TestCase):
    def test_chains_in_order_and_tears_down(self):
        calls: list[str] = []
        with _patched(calls):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.phase, "complete")
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(calls, ["validate", "start", "wait", "runner", "stop"])

    def test_endpoint_handed_to_runner(self):
        calls: list[str] = []
        with _patched(calls) as runner_mock:
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertEqual(res.endpoint, "http://node23:8000/v1")
        # _invoke_runner(hf_repo, endpoint, ...) — endpoint is the 2nd positional.
        repo_arg, endpoint_arg = runner_mock.call_args[0][:2]
        self.assertEqual(repo_arg, _REPO)
        self.assertEqual(endpoint_arg, "http://node23:8000/v1")


class OrchestrateFailurePathsTest(unittest.TestCase):
    def test_validation_failure_starts_nothing(self):
        calls: list[str] = []
        with _patched(calls, validation=_BAD):
            res = orch.orchestrate_eval("gated/model", judge_model=_JUDGE, slug="run-a")
        self.assertFalse(res.ok)
        self.assertEqual(res.phase, "validate")
        self.assertEqual(res.error, _BAD.error)
        self.assertEqual(calls, ["validate"])  # no start, no runner, no stop

    def test_start_failure_no_teardown(self):
        calls: list[str] = []
        with _patched(calls, start_rc=1):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertFalse(res.ok)
        self.assertEqual(res.phase, "serve")
        self.assertEqual(calls, ["validate", "start"])  # nothing to tear down

    def test_ready_timeout_tears_down_without_eval(self):
        calls: list[str] = []
        with _patched(calls, wait_rc=1):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertFalse(res.ok)
        self.assertEqual(res.phase, "serve")
        self.assertEqual(calls, ["validate", "start", "wait", "stop"])  # no runner

    def test_runner_nonzero_still_tears_down(self):
        calls: list[str] = []
        with _patched(calls, runner_rc=2):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertFalse(res.ok)
        self.assertEqual(res.phase, "evaluate")
        self.assertEqual(res.exit_code, 2)
        self.assertEqual(calls, ["validate", "start", "wait", "runner", "stop"])

    def test_runner_exception_still_tears_down(self):
        calls: list[str] = []
        with _patched(calls, runner_exc=RuntimeError("boom")):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertFalse(res.ok)
        self.assertEqual(res.phase, "evaluate")
        self.assertIn("boom", res.error or "")
        self.assertEqual(calls[-1], "stop")  # teardown ran despite the crash

    def test_start_exception_no_teardown(self):
        calls: list[str] = []
        with _patched(calls, start_exc=RuntimeError("sbatch missing")):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a")
        self.assertFalse(res.ok)
        self.assertEqual(res.phase, "serve")
        self.assertEqual(calls, ["validate", "start"])  # no job -> no stop


class OrchestrateStateIsolationTest(unittest.TestCase):
    def test_per_run_state_files_differ(self):
        seen: list[str] = []

        def _capture_start(args):
            seen.append(args.session_file)
            return 0

        with mock.patch.object(orch.hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(orch.vllm, "cmd_start", side_effect=_capture_start), \
             mock.patch.object(orch.vllm, "cmd_wait", return_value=0), \
             mock.patch.object(orch.vllm, "cmd_stop", return_value=0), \
             mock.patch.object(orch.vllm, "_read_state", return_value=_STATE), \
             mock.patch.object(orch, "_invoke_runner", return_value=0):
            orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="alpha")
            orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="beta")

        self.assertEqual(len(seen), 2)
        self.assertNotEqual(seen[0], seen[1])
        self.assertTrue(seen[0].endswith("alpha.env"))
        self.assertTrue(seen[1].endswith("beta.env"))
        self.assertIn(".jobs", seen[0])


class OrchestrateDryRunTest(unittest.TestCase):
    def test_dry_run_has_no_side_effects(self):
        calls: list[str] = []
        with _patched(calls):
            res = orch.orchestrate_eval(_REPO, judge_model=_JUDGE, slug="run-a",
                                        dry_run=True)
        self.assertTrue(res.ok)
        self.assertEqual(res.phase, "dry_run")
        self.assertEqual(calls, [])  # nothing invoked — pure preview
        joined = "\n".join(res.plan)
        self.assertIn("validate", joined)
        self.assertIn("--inference-backend dcc", joined)
        self.assertIn("--candidate-endpoint", joined)
        self.assertIn("run-a.env", joined)


if __name__ == "__main__":
    unittest.main()
