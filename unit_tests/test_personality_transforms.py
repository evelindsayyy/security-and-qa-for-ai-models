"""Tests for personality result transforms and loader parse path."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from personality.db.transforms import personality_run_row


class PersonalityTransformTest(unittest.TestCase):
    def test_parses_bfi_artifact(self) -> None:
        payload = {
            "test": "bfi",
            "model": "GPT 4.1 Mini",
            "timestamp": "2026-07-14T12:00:00+00:00",
            "summary": {
                "traits": {
                    "extraversion": 3.2,
                    "agreeableness": 4.1,
                    "conscientiousness": 3.8,
                    "neuroticism": 2.1,
                    "openness": 4.5,
                },
                "attempted": 44,
                "scored": 44,
                "coverage": 1.0,
            },
            "items": [{"id": 1, "scored": True}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260714T120000Z_bfi_GPT-4.1-Mini.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            row = personality_run_row(path)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["output_slug"], path.stem)
        self.assertEqual(row["test_key"], "bfi")
        self.assertEqual(row["gateway_model_id"], "GPT 4.1 Mini")
        self.assertEqual(row["n_items"], 1)
        self.assertEqual(row["scored"], 44)
        self.assertAlmostEqual(row["traits"]["openness"], 4.5)

    def test_parses_compass_artifact(self) -> None:
        payload = {
            "test": "compass",
            "model": "GPT 4.1 Mini",
            "timestamp": "2026-07-14T13:00:00+00:00",
            "summary": {
                "quadrant": "Libertarian Left",
                "axes": {
                    "economic": {"score": -40.0, "neg_pct": 70.0, "pos_pct": 30.0},
                    "social": {"score": -20.0, "neg_pct": 60.0, "pos_pct": 40.0},
                },
                "attempted": 20,
                "scored": 20,
                "coverage": 1.0,
            },
            "items": [{"id": 1, "choice": "A"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "20260714T130000Z_compass_GPT-4.1-Mini.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            row = personality_run_row(path)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["test_key"], "compass")
        self.assertEqual(row["summary"]["quadrant"], "Libertarian Left")
        self.assertEqual(row["n_items"], 1)

    def test_rejects_unknown_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text(json.dumps({"test": "nope", "model": "x"}), encoding="utf-8")
            self.assertIsNone(personality_run_row(path))


if __name__ == "__main__":
    unittest.main()
