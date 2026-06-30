"""Tests for run config fingerprinting."""

from __future__ import annotations

import unittest

from dbutils.run_fingerprint import (
    fingerprint,
    is_public_default,
    normalize_scan_config,
    normalize_safety_config,
    normalize_eval_config,
    normalize_benchmark_config,
)


class TestRunFingerprint(unittest.TestCase):
    def test_scan_fingerprint_stable(self):
        cfg = normalize_scan_config(hf_repo="gpt2")
        fp1 = fingerprint("scan", cfg)
        fp2 = fingerprint("scan", cfg)
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)

    def test_scan_public_default(self):
        cfg = normalize_scan_config(hf_repo="gpt2")
        self.assertTrue(is_public_default("scan", cfg))
        cfg_skip = normalize_scan_config(hf_repo="gpt2", skip_modelscan=True)
        self.assertFalse(is_public_default("scan", cfg_skip))

    def test_safety_public_default_base_only(self):
        cfg = normalize_safety_config(model="GPT 4.1 Mini", redteam_profile="base")
        self.assertTrue(is_public_default("safety", cfg))
        custom = normalize_safety_config(model="GPT 4.1 Mini", redteam_profile="rag")
        self.assertFalse(is_public_default("safety", custom))

    def test_eval_custom_not_public_default(self):
        cfg = normalize_eval_config(
            candidate="GPT 4.1 Mini",
            judge="Llama 4 Maverick",
            suite_key="custom_20260101T000000Z",
            max_tokens=2000,
        )
        self.assertFalse(is_public_default("eval", cfg))
        curated = normalize_eval_config(
            candidate="GPT 4.1 Mini",
            judge="Llama 4 Maverick",
            suite_key="it_support_v1",
            max_tokens=2000,
        )
        self.assertTrue(is_public_default("eval", curated))

    def test_benchmark_public_default(self):
        cfg = normalize_benchmark_config(benchmark_key="ifeval", model="gpt-5-chat")
        self.assertTrue(is_public_default("benchmark", cfg))


if __name__ == "__main__":
    unittest.main()
