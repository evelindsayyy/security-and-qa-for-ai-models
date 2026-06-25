"""
Tests for Hugging Face model intake validation (evaluator/hf_intake.py).

Fully offline: the network fetch is injected, so no Hugging Face calls. Covers
the repo-id allowlist (the security boundary before any subprocess) and the
exists / gated / architecture / size validation rules.

Run from repo root:
  uv run python -m unittest unit_tests.test_hf_intake -v
"""

from __future__ import annotations

import unittest

from evaluator import hf_intake as hf


def _info(**kw) -> "hf.ModelInfo":
    base = dict(repo_id="org/model", architectures=["LlamaForCausalLM"],
                num_params=7_000_000_000, gated=False)
    base.update(kw)
    return hf.ModelInfo(**base)


class RepoIdAllowlistTest(unittest.TestCase):
    def test_valid_ids(self) -> None:
        for ok in ("Qwen/Qwen2.5-7B-Instruct", "gpt2", "org/model-1.0", "a_b/c.d-e"):
            self.assertTrue(hf.is_valid_repo_id(ok), ok)

    def test_rejects_unsafe_ids(self) -> None:
        for bad in ("", "/x", "x/", "a/b/c", "a b", "../etc/passwd",
                    "a;rm -rf /", "a/b;c", "a|b", "a$b", "a/b/", "a..b"):
            self.assertFalse(hf.is_valid_repo_id(bad), bad)


class ValidateTest(unittest.TestCase):
    def _validate(self, repo_id, info):
        return hf.validate(repo_id, fetch=lambda _rid: info)

    def test_malformed_repo_id_rejected_before_any_fetch(self) -> None:
        called = []

        def fetch(rid):
            called.append(rid)
            return _info()

        res = hf.validate("a;rm -rf /", fetch=fetch)
        self.assertFalse(res.ok)
        self.assertIn("repo id", res.error.lower())
        self.assertEqual(called, [])          # allowlist runs first; never hits network

    def test_not_found(self) -> None:
        res = self._validate("org/missing", None)
        self.assertFalse(res.ok)
        self.assertIn("not found", res.error.lower())

    def test_gated_rejected(self) -> None:
        res = self._validate("org/model", _info(gated=True))
        self.assertFalse(res.ok)
        self.assertIn("gated", res.error.lower())

    def test_unsupported_architecture(self) -> None:
        res = self._validate("org/model", _info(architectures=["WhizBangForCausalLM"]))
        self.assertFalse(res.ok)
        self.assertIn("architecture", res.error.lower())

    def test_too_large_for_gpu(self) -> None:
        res = self._validate("org/huge", _info(num_params=70_000_000_000))
        self.assertFalse(res.ok)
        self.assertIn("large", res.error.lower())

    def test_unknown_size_is_allowed(self) -> None:
        # HF didn't report a param count — don't block on size.
        res = self._validate("org/model", _info(num_params=None))
        self.assertTrue(res.ok)

    def test_valid_model_passes(self) -> None:
        res = self._validate(
            "Qwen/Qwen2.5-7B-Instruct",
            _info(repo_id="Qwen/Qwen2.5-7B-Instruct", architectures=["Qwen2ForCausalLM"]))
        self.assertTrue(res.ok)
        self.assertIsNone(res.error)
        self.assertEqual(res.info.repo_id, "Qwen/Qwen2.5-7B-Instruct")


if __name__ == "__main__":
    unittest.main()
