"""Tests for safety/gateway_ids.py normalization."""

from __future__ import annotations

import unittest

from safety.gateway_ids import normalize_gateway_model_id


class NormalizeGatewayModelIdTest(unittest.TestCase):
    def test_display_name(self) -> None:
        self.assertEqual(normalize_gateway_model_id("GPT 4.1 Mini"), "gpt-4.1-mini")

    def test_duke_prefixed_label(self) -> None:
        self.assertEqual(normalize_gateway_model_id("duke-gpt-4.1-mini"), "gpt-4.1-mini")

    def test_promptfoo_provider_id(self) -> None:
        self.assertEqual(normalize_gateway_model_id("openai:chat:GPT 4.1 Mini"), "gpt-4.1-mini")

    def test_hf_repo_id_from_garak_target_name(self) -> None:
        self.assertEqual(
            normalize_gateway_model_id("Qwen/Qwen2.5-3B-Instruct"),
            "qwen__qwen2.5-3b-instruct",
        )

    def test_hf_repo_id_from_promptfoo_provider_id(self) -> None:
        self.assertEqual(
            normalize_gateway_model_id("openai:chat:Qwen/Qwen2.5-3B-Instruct"),
            "qwen__qwen2.5-3b-instruct",
        )

    def test_hf_repo_id_without_namespace(self) -> None:
        self.assertEqual(normalize_gateway_model_id("gpt2"), "gpt2")

    def test_empty_is_unknown(self) -> None:
        self.assertEqual(normalize_gateway_model_id(""), "unknown")


if __name__ == "__main__":
    unittest.main()
