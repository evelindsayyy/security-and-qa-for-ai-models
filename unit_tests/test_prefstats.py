"""
Synthetic self-tests for docs/validation-study/prefstats.py.

These pin each metric against a known value BEFORE any real survey data arrives
(the "verify the ruler before you measure" step from analysis_plan.md). Pure,
offline, deterministic — no CSVs, no network.

Run from repo root:
  uv run python -m unittest unit_tests.test_prefstats -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_VS = Path(__file__).resolve().parent.parent / "docs" / "validation-study"
sys.path.insert(0, str(_VS))

import prefstats as ps  # noqa: E402


class OrderAndConsensusTest(unittest.TestCase):
    def test_to_system_pref_undoes_order(self) -> None:
        # strong system X shown as Response 2, rater picks R2 -> recovers X
        self.assertEqual(ps.to_system_pref("R2", "Y", "X"), "X")
        self.assertEqual(ps.to_system_pref("R1", "X", "Y"), "X")
        self.assertEqual(ps.to_system_pref("tie", "X", "Y"), "tie")

    def test_preferred_model(self) -> None:
        self.assertEqual(ps.preferred_model("R1", "m1", "m2"), "m1")
        self.assertEqual(ps.preferred_model("R2", "m1", "m2"), "m2")
        self.assertIsNone(ps.preferred_model("tie", "m1", "m2"))

    def test_consensus_majority_and_split(self) -> None:
        self.assertEqual(ps.consensus(["X", "X", "Y"]), "X")     # 2/3 majority
        self.assertEqual(ps.consensus(["X", "X", "X"]), "X")
        self.assertEqual(ps.consensus(["X", "Y", "tie"]), ps.NO_CONSENSUS)  # 1-1-1
        self.assertEqual(ps.consensus([]), ps.NO_CONSENSUS)


class CohenKappaTest(unittest.TestCase):
    def test_perfect_agreement_is_one(self) -> None:
        self.assertEqual(ps.cohen_kappa(["X", "Y", "X", "Y"], ["X", "Y", "X", "Y"]), 1.0)

    def test_chance_agreement_is_zero(self) -> None:
        # po = pe = 0.5 -> kappa 0
        k = ps.cohen_kappa(["X", "X", "Y", "Y"], ["X", "Y", "X", "Y"])
        self.assertAlmostEqual(k, 0.0, places=6)

    def test_systematic_disagreement_is_negative(self) -> None:
        # same marginals (2 X / 2 Y each) but always opposite -> worse than chance
        self.assertAlmostEqual(
            ps.cohen_kappa(["X", "Y", "X", "Y"], ["Y", "X", "Y", "X"]), -1.0, places=6)


class FleissKappaTest(unittest.TestCase):
    def test_perfect_agreement_is_one(self) -> None:
        table = ps.labels_to_fleiss_table([["X", "X", "X"], ["Y", "Y", "Y"], ["X", "X", "X"]])
        self.assertAlmostEqual(ps.fleiss_kappa(table), 1.0, places=6)

    def test_rejects_unequal_raters(self) -> None:
        with self.assertRaises(ValueError):
            ps.fleiss_kappa([[3, 0], [2, 0]])   # 3 raters vs 2

    def test_partial_agreement_between_zero_and_one(self) -> None:
        table = ps.labels_to_fleiss_table(
            [["X", "X", "Y"], ["X", "Y", "Y"], ["X", "X", "X"], ["Y", "Y", "X"]])
        k = ps.fleiss_kappa(table)
        self.assertGreater(k, -1.0)
        self.assertLess(k, 1.0)


class PointBiserialTest(unittest.TestCase):
    def test_positive_correlation(self) -> None:
        self.assertGreater(ps.point_biserial([0, 0, 1, 1], [1, 2, 3, 4]), 0.85)

    def test_negative_correlation(self) -> None:
        self.assertLess(ps.point_biserial([0, 0, 1, 1], [4, 3, 2, 1]), -0.85)

    def test_no_variance_is_zero(self) -> None:
        self.assertEqual(ps.point_biserial([1, 1, 1, 1], [1, 2, 3, 4]), 0.0)


class BradleyTerryTest(unittest.TestCase):
    def test_always_winner_ranks_highest(self) -> None:
        pairs = [("C", "A")] * 4 + [("C", "B")] * 4 + [("B", "A")] * 4
        ranked = ps.bradley_terry_ranking(["A", "B", "C"], pairs)
        names = [s for s, _ in ranked]
        self.assertEqual(names[0], "C")     # beats everyone
        self.assertEqual(names[-1], "A")    # loses to everyone
        thetas = dict(ranked)
        self.assertGreater(thetas["C"], thetas["B"])
        self.assertGreater(thetas["B"], thetas["A"])

    def test_empty_pairs_flat(self) -> None:
        self.assertEqual(list(ps.bradley_terry(3, [])), [0.0, 0.0, 0.0])


class KappaReadingTest(unittest.TestCase):
    def test_thresholds(self) -> None:
        self.assertEqual(ps.kappa_reading(-0.1), "poor")
        self.assertEqual(ps.kappa_reading(0.5), "moderate")
        self.assertEqual(ps.kappa_reading(0.7), "substantial")
        self.assertEqual(ps.kappa_reading(0.95), "almost perfect")


if __name__ == "__main__":
    unittest.main()
