"""
Tests for frontend/model_identity.py — the shared slug helpers for the two
identity spaces (gateway id vs HF repo id) that stay intentionally separate.

  uv run python -m unittest unit_tests.test_model_identity -v
"""

from __future__ import annotations

import unittest

from frontend.model_identity import gateway_slug, hf_repo_id, hf_slug


class GatewaySlugTest(unittest.TestCase):
    def test_normalizes_display_name(self) -> None:
        self.assertEqual(gateway_slug("GPT 4.1 Mini"), "gpt-4.1-mini")

    def test_strips_duke_prefix(self) -> None:
        self.assertEqual(gateway_slug("duke-gpt-4.1-mini"), "gpt-4.1-mini")

    def test_empty_is_unknown(self) -> None:
        self.assertEqual(gateway_slug(""), "unknown")


class HfSlugRoundTripTest(unittest.TestCase):
    def test_repo_id_to_slug(self) -> None:
        self.assertEqual(hf_slug("BAAI/bge-small-en-v1.5"), "BAAI--bge-small-en-v1.5")

    def test_slug_to_repo_id(self) -> None:
        self.assertEqual(hf_repo_id("BAAI--bge-small-en-v1.5"), "BAAI/bge-small-en-v1.5")

    def test_round_trip(self) -> None:
        for repo_id in ("gpt2", "BAAI/bge-small-en-v1.5", "facebook/opt-125m"):
            with self.subTest(repo_id=repo_id):
                self.assertEqual(hf_repo_id(hf_slug(repo_id)), repo_id)

    def test_slug_without_separator_is_unchanged(self) -> None:
        self.assertEqual(hf_repo_id("gpt2"), "gpt2")


if __name__ == "__main__":
    unittest.main()
