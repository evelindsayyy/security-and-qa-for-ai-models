"""
Tests for the eval-run launcher's Hugging Face model path.

/eval-run/new lets you run a gateway model OR specify an HF model. The HF path
validates the repo (evaluator/hf_intake) before any run; actually serving an HF
model on the DCC is a later milestone, so this validates + reports. All offline
(the HF Hub validation is mocked).

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_hf_launch -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from evaluator import hf_intake  # noqa: E402
from frontend import create_app, eval_launch  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_GOOD = hf_intake.ValidationResult(
    True, None,
    hf_intake.ModelInfo(repo_id="Qwen/Qwen2.5-7B-Instruct",
                        architectures=["Qwen2ForCausalLM"],
                        num_params=7_000_000_000, gated=False))
_BAD = hf_intake.ValidationResult(
    False, "model is gated/private; not supported in the MVP")


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        # Keep the candidate allowlist offline/deterministic (no gateway call).
        p = mock.patch.object(eval_launch, "candidate_models",
                              return_value=eval_launch._CANDIDATE_FALLBACK)
        p.start()
        self.addCleanup(p.stop)


class HfLaunchFormTest(_Base):
    def test_new_page_offers_gateway_and_hf_sources(self) -> None:
        r = _client().get("/eval-run/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'name="hf_repo"', r.data)        # the HF field
        self.assertIn(b'name="source"', r.data)         # gateway/hf toggle
        self.assertIn(b'name="candidate"', r.data)      # gateway dropdown still there


class HfLaunchValidateTest(_Base):
    def test_validate_hf_candidate_shapes_result(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD):
            out = eval_launch.validate_hf_candidate("Qwen/Qwen2.5-7B-Instruct")
        self.assertTrue(out["ok"])
        self.assertEqual(out["architectures"], ["Qwen2ForCausalLM"])
        self.assertEqual(out["repo_id"], "Qwen/Qwen2.5-7B-Instruct")

    def test_post_hf_valid_launches_on_dcc(self) -> None:
        # DCC serving is now wired: a servable HF model launches the orchestrator
        # and redirects to the running detail (see test_eval_dcc_launch for full
        # coverage). The custom-form HF path below stays validate-only.
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(eval_launch, "start_dcc_run",
                               return_value=("stem123", False)) as sr:
            r = _client().post("/eval-run/start",
                               data={"source": "hf",
                                     "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                                     "judge": "Llama 4 Maverick",
                                     "suite": "it_support_v1", "max_tokens": "2000"})
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()

    def test_post_hf_invalid_shows_reason(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_BAD):
            r = _client().post("/eval-run/start",
                               data={"source": "hf", "hf_repo": "org/gated"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gated", r.data)


class CustomHfLaunchTest(_Base):
    """The 'bring your own questions' form supports HF models the same way the
    standard start-run form does: a gateway/hf source toggle, an HF repo field,
    and a /eval-run/start-custom HF branch that validates the model (serving is
    the later DCC milestone)."""

    def test_custom_form_offers_hf_source(self) -> None:
        r = _client().get("/eval-run/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'id="hf_repo_c"', r.data)   # the custom form's HF field

    def test_post_custom_hf_valid_shows_ready(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD):
            r = _client().post("/eval-run/start-custom",
                               data={"source": "hf",
                                     "hf_repo": "Qwen/Qwen2.5-7B-Instruct"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Qwen2ForCausalLM", r.data)

    def test_post_custom_hf_invalid_shows_reason(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_BAD):
            r = _client().post("/eval-run/start-custom",
                               data={"source": "hf", "hf_repo": "org/gated"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gated", r.data)

    def test_post_custom_hf_does_not_start_a_run(self) -> None:
        # HF serving isn't wired yet — the custom HF path validates only, never
        # spawning a runner, exactly like the standard HF path.
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(eval_launch, "start_run") as sr:
            _client().post("/eval-run/start-custom",
                           data={"source": "hf",
                                 "hf_repo": "Qwen/Qwen2.5-7B-Instruct"})
        sr.assert_not_called()

    def test_post_custom_gateway_still_starts_a_run(self) -> None:
        # Regression: the gateway custom path is unchanged by the HF branch.
        with mock.patch.object(eval_launch, "start_run",
                               return_value=("slug123", False)) as sr, \
             mock.patch.object(eval_launch, "write_custom_suite",
                               return_value="custom_x"), \
             mock.patch.object(eval_launch, "validate_launch", return_value=None):
            r = _client().post(
                "/eval-run/start-custom",
                data={"candidate": "gpt-5-chat", "judge": "Llama 4 Maverick",
                      "max_tokens": "2000",
                      "questions": '{"question": "q", "reference": "r"}'})
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()


if __name__ == "__main__":
    unittest.main()
