"""
Tests for the safety pre-flight CLI (safety/hf_preflight.py).

Fully offline: patches evaluator.hf_intake.validate (not fetch_model_info —
that function is bound as a default argument inside hf_intake.validate at
module-load time, so patching it later would not affect existing callers;
patching validate() itself, looked up fresh on every call, does). Covers
exit codes and stdout/stderr shape for the reject vs. accept paths, since
those are what a shell script (e.g. the DCC launcher) would branch on.

Run from repo root:
  uv run python -m unittest unit_tests.test_hf_preflight -v
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from evaluator import hf_intake
from safety import hf_preflight


def _info(**kw) -> hf_intake.ModelInfo:
    base = dict(repo_id="Qwen/Qwen2.5-3B-Instruct", architectures=["Qwen2ForCausalLM"],
                num_params=3_000_000_000, gated=False)
    base.update(kw)
    return hf_intake.ModelInfo(**base)


class CheckRepoTest(unittest.TestCase):
    def test_delegates_to_hf_intake_validate(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _info())
        with mock.patch.object(hf_intake, "validate", return_value=canned) as m:
            result = hf_preflight.check_repo("Qwen/Qwen2.5-3B-Instruct")
        m.assert_called_once_with("Qwen/Qwen2.5-3B-Instruct")
        self.assertTrue(result.ok)
        self.assertEqual(result.info.repo_id, "Qwen/Qwen2.5-3B-Instruct")


class MainTest(unittest.TestCase):
    def test_rejects_bad_repo_id_exit_1(self) -> None:
        # Malformed ids are rejected by the allowlist before any network call,
        # so this is deterministic offline with no mocking needed.
        err = io.StringIO()
        with redirect_stderr(err):
            code = hf_preflight.main(["a;rm -rf /"])
        self.assertEqual(code, 1)
        self.assertIn("REJECTED", err.getvalue())

    def test_rejects_oversized_model_exit_1(self) -> None:
        canned = hf_intake.ValidationResult(False, "model is too large (~70B params) for a single a5000")
        err = io.StringIO()
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            with redirect_stderr(err):
                code = hf_preflight.main(["org/huge"])
        self.assertEqual(code, 1)
        self.assertIn("large", err.getvalue().lower())

    def test_accepts_valid_model_exit_0_text(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _info())
        out = io.StringIO()
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            with redirect_stdout(out):
                code = hf_preflight.main(["Qwen/Qwen2.5-3B-Instruct"])
        self.assertEqual(code, 0)
        self.assertIn("OK Qwen/Qwen2.5-3B-Instruct", out.getvalue())
        self.assertIn("3.0B", out.getvalue())

    def test_accepts_valid_model_exit_0_json(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _info())
        out = io.StringIO()
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            with redirect_stdout(out):
                code = hf_preflight.main(["Qwen/Qwen2.5-3B-Instruct", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["repo_id"], "Qwen/Qwen2.5-3B-Instruct")
        self.assertEqual(payload["num_params"], 3_000_000_000)

    def test_unknown_param_count_prints_unknown(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _info(num_params=None))
        out = io.StringIO()
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            with redirect_stdout(out):
                code = hf_preflight.main(["Qwen/Qwen2.5-3B-Instruct"])
        self.assertEqual(code, 0)
        self.assertIn("params=unknown", out.getvalue())


if __name__ == "__main__":
    unittest.main()
