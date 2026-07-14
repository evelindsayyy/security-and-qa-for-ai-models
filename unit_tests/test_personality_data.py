"""Tests for personality result listing helpers."""

from __future__ import annotations

import unittest

from frontend.personality_data import _dedupe_twin_artifacts


class TestPersonalityDataDedupe(unittest.TestCase):
    def test_prefers_canonical_stem_over_bfi_mirror(self) -> None:
        rows = [
            {
                "test": "bfi",
                "slug": "bfi_Llama_3.3_20260713_115515",
                "model": "Llama 3.3",
                "timestamp_raw": "2026-07-13T15:55:39+00:00",
            },
            {
                "test": "bfi",
                "slug": "20260713T155439Z_bfi_Llama-3.3",
                "model": "Llama 3.3",
                "timestamp_raw": "2026-07-13T15:55:39+00:00",
            },
        ]
        out = _dedupe_twin_artifacts(rows)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["slug"], "20260713T155439Z_bfi_Llama-3.3")

    def test_keeps_distinct_runs_for_same_model(self) -> None:
        rows = [
            {
                "test": "bfi",
                "slug": "20260713T155439Z_bfi_Llama-3.3",
                "model": "Llama 3.3",
                "timestamp_raw": "2026-07-13T15:55:39+00:00",
            },
            {
                "test": "bfi",
                "slug": "20260713T160000Z_bfi_Llama-3.3",
                "model": "Llama 3.3",
                "timestamp_raw": "2026-07-13T16:00:00+00:00",
            },
        ]
        out = _dedupe_twin_artifacts(rows)
        self.assertEqual(len(out), 2)

    def test_keeps_bfi_and_compass_for_same_model(self) -> None:
        rows = [
            {
                "test": "bfi",
                "slug": "20260713T155439Z_bfi_Llama-3.3",
                "model": "Llama 3.3",
                "timestamp_raw": "2026-07-13T15:55:39+00:00",
            },
            {
                "test": "compass",
                "slug": "20260713T155439Z_compass_Llama-3.3",
                "model": "Llama 3.3",
                "timestamp_raw": "2026-07-13T15:55:39+00:00",
            },
        ]
        out = _dedupe_twin_artifacts(rows)
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
