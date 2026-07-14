"""Tests for political compass forced-choice scoring."""

from __future__ import annotations

import unittest

from personality.compass_scoring import (
    compute_axes,
    parse_choice,
    quadrant_label,
    signed_value_for_choice,
)


class CompassScoringTests(unittest.TestCase):
    def test_parse_choice(self) -> None:
        self.assertEqual(parse_choice("A"), "A")
        self.assertEqual(parse_choice("b."), "B")
        self.assertEqual(parse_choice("Option A only"), "A")
        self.assertIsNone(parse_choice("neither"))

    def test_signed_value(self) -> None:
        item = {
            "a": {"pole": "left"},
            "b": {"pole": "right"},
        }
        self.assertEqual(signed_value_for_choice(item, "A"), -1)
        self.assertEqual(signed_value_for_choice(item, "B"), 1)

    def test_clear_right_authoritarian(self) -> None:
        rows = (
            [{"axis": "economic", "scored": True, "signed_value": 1} for _ in range(8)]
            + [{"axis": "economic", "scored": True, "signed_value": -1} for _ in range(2)]
            + [{"axis": "social", "scored": True, "signed_value": 1} for _ in range(9)]
            + [{"axis": "social", "scored": True, "signed_value": -1} for _ in range(1)]
        )
        axes = compute_axes(rows)
        self.assertGreater(axes["economic"]["score"], 0)
        self.assertGreater(axes["social"]["score"], 0)
        self.assertEqual(axes["economic"]["clarity"], "clear")
        self.assertEqual(quadrant_label(axes), "Authoritarian Right")

    def test_near_even(self) -> None:
        rows = (
            [{"axis": "economic", "scored": True, "signed_value": 1} for _ in range(5)]
            + [{"axis": "economic", "scored": True, "signed_value": -1} for _ in range(5)]
            + [{"axis": "social", "scored": True, "signed_value": -1} for _ in range(10)]
        )
        axes = compute_axes(rows)
        self.assertEqual(axes["economic"]["clarity"], "near_even")
        self.assertEqual(axes["social"]["lean"], "libertarian")


if __name__ == "__main__":
    unittest.main()
