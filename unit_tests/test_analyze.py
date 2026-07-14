"""
End-to-end test for docs/validation-study/analyze.py on SYNTHETIC labels.

Verifies the join + every aggregate (consensus, Fleiss κ, judge-vs-human κ,
position/length bias, Bradley-Terry, DPO triples) and the Qualtrics CSV parser —
all offline, no real survey needed. Pins the pipeline so it's ready the moment the
rater CSVs land.

Run from repo root:
  uv run python -m unittest unit_tests.test_analyze -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_VS = Path(__file__).resolve().parent.parent / "docs" / "validation-study"
sys.path.insert(0, str(_VS))

try:
    import analyze as az  # noqa: E402
    import prefstats as ps  # noqa: E402
except Exception as exc:  # pragma: no cover
    # analyze/prefstats need numpy; numpy 2.x PyPI wheels require x86-64-v2, which
    # some shared CI runners lack (RuntimeError on import). Skip the whole module
    # there rather than error — these tests still run wherever numpy imports.
    raise unittest.SkipTest(f"validation-study numpy stack unavailable: {exc}")

QWEN, MINI, NANO = "Qwen2.5-7B-Instruct", "GPT 4.1 Mini", "GPT 4.1 Nano"

ITEM_POOL = {
    "itm-001": {"item_id": "itm-001", "source": "s1", "prompt": "p1",
                "task_type": "email", "target_model": QWEN, "opponent_model": MINI},
    "itm-002": {"item_id": "itm-002", "source": "s2", "prompt": "p2",
                "task_type": "plain", "target_model": QWEN, "opponent_model": NANO},
}
RESPONSES = {
    ("s1", QWEN): "a thorough qwen answer that is clearly the longer one",
    ("s1", MINI): "short mini",
    ("s2", QWEN): "q2",
    ("s2", NANO): "a nano answer that is clearly longer than q2",
}
# rater_map: (rater, item) -> shown order
RATER_MAP = {
    ("01", "itm-001"): {"slot": 1, "r1": QWEN, "r2": MINI},
    ("02", "itm-001"): {"slot": 2, "r1": MINI, "r2": QWEN},
    ("03", "itm-001"): {"slot": 3, "r1": QWEN, "r2": MINI},
    ("04", "itm-002"): {"slot": 1, "r1": QWEN, "r2": NANO},
    ("05", "itm-002"): {"slot": 2, "r1": NANO, "r2": QWEN},
    ("06", "itm-002"): {"slot": 3, "r1": QWEN, "r2": NANO},
}
# picks: itm-001 -> all prefer Qwen; itm-002 -> Nano, Nano, tie
LABELS = [
    ("01", "itm-001", "R1"),   # Qwen
    ("02", "itm-001", "R2"),   # Qwen (shown 2nd)
    ("03", "itm-001", "R1"),   # Qwen
    ("04", "itm-002", "R2"),   # Nano (shown 2nd)
    ("05", "itm-002", "R1"),   # Nano
    ("06", "itm-002", "tie"),
]


class JoinTest(unittest.TestCase):
    def test_prefs_and_consensus(self) -> None:
        prefs = az.human_prefs_by_item(LABELS, RATER_MAP)
        self.assertEqual(prefs["itm-001"], [QWEN, QWEN, QWEN])
        self.assertEqual(sorted(prefs["itm-002"]), sorted([NANO, NANO, ps.TIE]))
        cons = az.consensus_by_item(prefs)
        self.assertEqual(cons["itm-001"], QWEN)
        self.assertEqual(cons["itm-002"], NANO)      # 2/3 majority over the tie

    def test_human_human_kappa_in_range(self) -> None:
        prefs = az.human_prefs_by_item(LABELS, RATER_MAP)
        k = az.human_human_kappa(prefs)
        self.assertIsNotNone(k)
        self.assertGreaterEqual(k, -1.0)
        self.assertLessEqual(k, 1.0)


class JudgeAndBiasTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prefs = az.human_prefs_by_item(LABELS, RATER_MAP)
        self.cons = az.consensus_by_item(self.prefs)

    def test_judge_perfect_agreement(self) -> None:
        judge = {"itm-001": QWEN, "itm-002": NANO}
        out = az.judge_vs_human(self.cons, judge)
        self.assertEqual(out["n"], 2)
        self.assertEqual(out["kappa"], 1.0)
        self.assertEqual(out["pct"], 1.0)

    def test_judge_partial_agreement(self) -> None:
        judge = {"itm-001": MINI, "itm-002": NANO}   # 1 of 2 matches
        out = az.judge_vs_human(self.cons, judge)
        self.assertEqual(out["pct"], 0.5)

    def test_position_bias(self) -> None:
        # non-tie picks: R1,R2,R1,R2,R1 -> 3/5 R1
        self.assertAlmostEqual(az.position_bias_human(LABELS), 0.6, places=6)

    def test_length_bias_longer_won(self) -> None:
        lb = az.length_bias(self.cons, ITEM_POOL, RESPONSES)
        self.assertEqual(lb["n"], 2)
        self.assertEqual(lb["longer_won_rate"], 1.0)     # longer answer won both


class RankingAndDpoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cons = az.consensus_by_item(az.human_prefs_by_item(LABELS, RATER_MAP))

    def test_bradley_terry_orders_nano_over_qwen_over_mini(self) -> None:
        # Qwen beat Mini; Nano beat Qwen  ->  Nano > Qwen > Mini
        ranked = az.bradley_terry_ranking(self.cons, ITEM_POOL)
        names = [s for s, _ in ranked]
        self.assertEqual(names[0], NANO)
        self.assertEqual(names[-1], MINI)

    def test_dpo_triples(self) -> None:
        triples = az.dpo_triples(self.cons, ITEM_POOL, RESPONSES)
        self.assertEqual(len(triples), 2)
        by_prompt = {t["prompt"]: t for t in triples}
        self.assertEqual(by_prompt["p1"]["chosen"], RESPONSES[("s1", QWEN)])
        self.assertEqual(by_prompt["p1"]["rejected"], RESPONSES[("s1", MINI)])
        self.assertEqual(by_prompt["p2"]["chosen"], RESPONSES[("s2", NANO)])


class QualtricsParseTest(unittest.TestCase):
    def test_parses_export_tags_and_answers(self) -> None:
        csv_text = (
            'name,itm_001,itm_002\n'
            '"Name","Task: ...","Task: ..."\n'
            '"{""ImportId"":""x""}","{""ImportId"":""a""}","{""ImportId"":""b""}"\n'
            '"Alice","Response 1","About the same"\n'
        )
        labels = az.parse_qualtrics_csv(csv_text, "03")
        self.assertIn(("03", "itm-001", "R1"), labels)
        self.assertIn(("03", "itm-002", ps.TIE), labels)


if __name__ == "__main__":
    unittest.main()
