"""
Tests for the eval-run launcher's DCC path (Hugging Face → serve → eval → teardown).

The standard /eval-run/start form's HF source now LAUNCHES an eval on the DCC via
`evaluator.dcc_orchestrate`: a servable model is validated, then served + evaluated
+ torn down. Fully offline — hf validation, the orchestrator subprocess spawn, and
the phase log are all mocked, so no Hugging Face calls, no Slurm, no GPU.

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_dcc_launch -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from evaluator import hf_intake  # noqa: E402
from frontend import create_app, eval_launch  # noqa: E402

_GOOD = hf_intake.ValidationResult(
    True, None,
    hf_intake.ModelInfo(repo_id="Qwen/Qwen2.5-7B-Instruct",
                        architectures=["Qwen2ForCausalLM"],
                        num_params=7_000_000_000, gated=False))
_BAD = hf_intake.ValidationResult(
    False, "model is gated/private; not supported in the MVP")

_REPO = "Qwen/Qwen2.5-7B-Instruct"
_JUDGE = "Llama 4 Maverick"


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        p = mock.patch.object(eval_launch, "candidate_models",
                              return_value=eval_launch._CANDIDATE_FALLBACK)
        p.start()
        self.addCleanup(p.stop)


class DccLaunchRouteTest(_Base):
    def test_valid_hf_launches_dcc_and_redirects(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(eval_launch, "start_dcc_run",
                               return_value=("stem123", False)) as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": _REPO,
                                     "judge": _JUDGE, "suite": "it_support_v1",
                                     "max_tokens": "2000"})
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()
        self.assertEqual(sr.call_args[0][0], _REPO)  # candidate = the HF repo

    def test_invalid_hf_shows_reason_no_launch(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_BAD), \
             mock.patch.object(eval_launch, "start_dcc_run") as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": "org/gated",
                                     "judge": _JUDGE, "suite": "it_support_v1",
                                     "max_tokens": "2000"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gated", r.data)
        sr.assert_not_called()

    def test_bad_judge_rejected_400_no_launch(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(eval_launch, "start_dcc_run") as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": _REPO,
                                     "judge": "not-a-judge", "suite": "it_support_v1",
                                     "max_tokens": "2000"})
        self.assertEqual(r.status_code, 400)
        sr.assert_not_called()

    def test_gateway_path_unchanged(self) -> None:
        with mock.patch.object(eval_launch, "start_run",
                               return_value=("slug1", False)) as sr, \
             mock.patch.object(eval_launch, "validate_launch", return_value=None):
            r = _client().post("/eval-run/start",
                               data={"candidate": "gpt-5-chat", "judge": _JUDGE,
                                     "suite": "it_support_v1", "max_tokens": "2000"})
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()


class DccValidateParamsTest(_Base):
    def test_good_params_pass(self) -> None:
        self.assertIsNone(
            eval_launch.validate_dcc_params(_REPO, _JUDGE, "it_support_v1", 2000))

    def test_same_family_judge_rejected(self) -> None:
        # A Llama candidate + a Llama judge violates the MT-Bench cross-family rule.
        err = eval_launch.validate_dcc_params(
            "meta-llama/Llama-3.1-8B-Instruct", "Llama 4 Maverick", "it_support_v1", 2000)
        self.assertIsNotNone(err)
        self.assertIn("family", err)

    def test_bad_suite_rejected(self) -> None:
        self.assertIsNotNone(
            eval_launch.validate_dcc_params(_REPO, _JUDGE, "no_such_suite", 2000))

    def test_bad_max_tokens_rejected(self) -> None:
        self.assertIsNotNone(
            eval_launch.validate_dcc_params(_REPO, _JUDGE, "it_support_v1", 999999))


class DccBuildCommandTest(_Base):
    def test_command_targets_orchestrator_with_dcc_args(self) -> None:
        cmd = eval_launch.build_dcc_command(_REPO, _JUDGE, "it_support_v1", 2000, "stemX")
        self.assertIn("evaluator.dcc_orchestrate", " ".join(cmd))
        self.assertIn("--hf-repo", cmd)
        self.assertIn(_REPO, cmd)
        self.assertIn("--judge-model", cmd)
        self.assertIn("--output-name", cmd)
        self.assertIn("stemX", cmd)
        self.assertIn("--slug", cmd)


class DccPhaseStatusTest(_Base):
    def _write_log(self, stem: str, body: str):
        eval_launch.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        log = eval_launch.RESULTS_DIR / f"{stem}.log"
        log.write_text(body, encoding="utf-8")
        self.addCleanup(lambda: log.unlink(missing_ok=True))
        return log

    def test_phase_parsed_returns_last_marker(self) -> None:
        log = self._write_log("phase_a", "=== command ===\nPHASE: provisioning\nPHASE: serving\n")
        self.assertEqual(eval_launch._dcc_phase(log), "serving")

    def test_phase_none_for_non_dcc_log(self) -> None:
        log = self._write_log("phase_b", "Runner started\n[1/12] q1 overall=4.0\n")
        self.assertIsNone(eval_launch._dcc_phase(log))

    def test_status_includes_phase_for_running_dcc(self) -> None:
        stem = "20260707T000001Z_it_support_v1_Qwen-Qwen2.5-7B-Instruct"
        self._write_log(stem, "PHASE: serving\n")
        fake = mock.Mock()
        fake.poll.return_value = None  # process alive
        eval_launch._RUNNING[stem] = fake
        self.addCleanup(lambda: eval_launch._RUNNING.pop(stem, None))
        st = eval_launch.get_status(stem)
        self.assertEqual(st["status"], "running")
        self.assertEqual(st.get("phase"), "serving")


if __name__ == "__main__":
    unittest.main()
