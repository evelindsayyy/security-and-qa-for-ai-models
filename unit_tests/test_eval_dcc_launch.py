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

import json
import os
import tempfile
import unittest
from pathlib import Path
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
_SCAN_OK = {
    "ok": True,
    "repo_id": _REPO,
    "status": "complete",
    "severity_tier": "low",
    "overall_risk_score": 0,
    "path": "scanner/output/Qwen--Qwen2.5-7B-Instruct/scan_result.json",
}


def _client():
    # /eval-run/start is @require_login, which checks for a session user —
    # establish an allowlisted signed-in session (auth is disabled in _Base
    # setUp, so any netid is allowlisted).
    client = create_app(test_config={"TESTING": True, "SECRET_KEY": "test"}).test_client()
    with client.session_transaction() as sess:
        sess["view_mode"] = "private"
        sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}
    return client


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        # /eval-run/start is @require_login; disable auth for these route tests
        # (auth reads AUTH_ENABLED per request, and the real .env turns it on).
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        p = mock.patch.object(eval_launch, "candidate_models",
                              return_value=eval_launch._CANDIDATE_FALLBACK)
        p.start()
        self.addCleanup(p.stop)


class DccLaunchRouteTest(_Base):
    def test_valid_hf_launches_dcc_and_redirects(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(eval_launch, "validate_hf_scan_gate", return_value=_SCAN_OK), \
             mock.patch.object(eval_launch, "start_dcc_run",
                               return_value=("stem123", False)) as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": _REPO,
                                     "judge": _JUDGE, "suite": "it_support_v1",
                                     "max_tokens": "2000"})
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()
        self.assertEqual(sr.call_args[0][0], _REPO)  # candidate = the HF repo

    def test_missing_scan_blocks_hf_launch(self) -> None:
        blocked = {**_SCAN_OK, "ok": False, "error": "security scan required"}
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(eval_launch, "validate_hf_scan_gate", return_value=blocked), \
             mock.patch.object(eval_launch, "start_dcc_run") as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": _REPO,
                                     "judge": _JUDGE, "suite": "it_support_v1",
                                     "max_tokens": "2000"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"security scan required", r.data)
        sr.assert_not_called()

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
             mock.patch.object(eval_launch, "validate_hf_scan_gate", return_value=_SCAN_OK), \
             mock.patch.object(eval_launch, "start_dcc_run") as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": _REPO,
                                     "judge": "not-a-judge", "suite": "it_support_v1",
                                     "max_tokens": "2000"})
        self.assertEqual(r.status_code, 400)
        sr.assert_not_called()

    def test_gateway_path_unchanged(self) -> None:
        with mock.patch.object(eval_launch, "start_run",
                               return_value=("slug1", False, "public")) as sr, \
             mock.patch.object(eval_launch, "validate_launch", return_value=None), \
             mock.patch("frontend.pipeline.require_ready_for_downstream",
                        return_value=None):
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


class HfScanGateTest(_Base):
    def _scan_path(self, data: dict | None):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        path = Path(td.name) / "scan_result.json"
        if data is not None:
            path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_scan_gate_allows_completed_low_scan(self) -> None:
        path = self._scan_path({
            "status": "complete",
            "severity_tier": "low",
            "overall_risk_score": 0,
        })
        with mock.patch.object(eval_launch, "_scan_result_path", return_value=path):
            out = eval_launch.validate_hf_scan_gate(_REPO)
        self.assertTrue(out["ok"], out["error"])

    def test_scan_gate_blocks_missing_scan(self) -> None:
        path = self._scan_path(None)
        with mock.patch.object(eval_launch, "_scan_result_path", return_value=path):
            out = eval_launch.validate_hf_scan_gate(_REPO)
        self.assertFalse(out["ok"])
        self.assertIn("security scan required", out["error"])

    def test_scan_gate_blocks_high_risk_scan(self) -> None:
        path = self._scan_path({
            "status": "complete",
            "severity_tier": "critical",
            "overall_risk_score": 95,
        })
        with mock.patch.object(eval_launch, "_scan_result_path", return_value=path):
            out = eval_launch.validate_hf_scan_gate(_REPO)
        self.assertFalse(out["ok"])
        self.assertIn("blocked", out["error"])


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
        self.assertEqual(st["status"], "serving")
        self.assertEqual(st.get("phase"), "serving")

    def test_status_done_when_results_complete(self) -> None:
        stem = "20260707T000002Z_it_support_v1_Qwen-Qwen2.5-7B-Instruct"
        path = eval_launch.RESULTS_DIR / f"{stem}.jsonl"
        eval_launch.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(["{}"] * 12) + "\n", encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        with mock.patch.object(eval_launch, "suite_question_count", return_value=12):
            st = eval_launch.get_status(stem)
        self.assertEqual(st["status"], "done")


if __name__ == "__main__":
    unittest.main()
