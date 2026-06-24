"""
Tests for the HF-model intake page (link-based self-serve intake, MVP).

Flask test client; the Hugging Face Hub validation is mocked so the tests run
offline. Covers the GET form, a valid model (shows details), and an invalid one
(shows the reason).

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_intake -v
"""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from evaluator import hf_intake  # noqa: E402
from frontend import create_app  # noqa: E402


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


_GOOD = hf_intake.ValidationResult(
    True, None,
    hf_intake.ModelInfo(repo_id="Qwen/Qwen2.5-7B-Instruct",
                        architectures=["Qwen2ForCausalLM"],
                        num_params=7_000_000_000, gated=False))
_BAD = hf_intake.ValidationResult(
    False, "model is gated/private; not supported in the MVP")


class AddModelPageTest(unittest.TestCase):
    def test_get_renders_form(self) -> None:
        r = _client().get("/eval-run/add-model")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'name="repo_id"', r.data)

    def test_post_valid_shows_model_details(self) -> None:
        with mock.patch("frontend.eval_intake.hf_intake.validate", return_value=_GOOD):
            r = _client().post("/eval-run/add-model",
                               data={"repo_id": "Qwen/Qwen2.5-7B-Instruct"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Qwen2ForCausalLM", r.data)        # architecture surfaced

    def test_post_invalid_shows_error(self) -> None:
        with mock.patch("frontend.eval_intake.hf_intake.validate", return_value=_BAD):
            r = _client().post("/eval-run/add-model", data={"repo_id": "org/gated"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gated", r.data)                   # the reason surfaced


if __name__ == "__main__":
    unittest.main()
