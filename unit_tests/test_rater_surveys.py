"""
Invariants for the 6-rater / 60-item / 3-label survey allocation
(docs/validation-study/build_rater_surveys.py).

Offline: reads the frozen item_pool.jsonl and checks the pure allocation — no
rendering, no network. Pins the design: balanced 60, exactly-3 labels per item,
exactly-30 per rater, both opponents 50/50.

Run from repo root:
  uv run python -m unittest unit_tests.test_rater_surveys -v
"""

from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

_VS = Path(__file__).resolve().parent.parent / "docs" / "validation-study"
sys.path.insert(0, str(_VS))

import build_rater_surveys as brs  # noqa: E402


class RaterAllocationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pool = brs.load_pool()
        self.items = brs.select_items(self.pool)
        self.partitions = brs.complementary_partitions()
        self.rater_items, self.item_trio = brs.assign(self.items)
        self.src = {it["item_id"]: it["source"] for it in self.pool}

    def test_pool_is_108(self) -> None:
        self.assertEqual(len(self.pool), 108)

    def test_selects_60_with_opponents_balanced(self) -> None:
        self.assertEqual(len(self.items), brs.N_ITEMS)  # 60
        opp = Counter(it["opponent_model"] for it in self.items)
        self.assertEqual(opp["GPT 4.1 Mini"], 30)
        self.assertEqual(opp["GPT 4.1 Nano"], 30)

    def test_task_types_balanced(self) -> None:
        # round-robin picks 5 prompts/type × 2 opponents = 10 items/type
        by_type = Counter(it["task_type"] for it in self.items)
        for tt, n in by_type.items():
            self.assertEqual(n, 10, f"{tt} has {n} items")

    def test_every_item_includes_dpo_target(self) -> None:
        self.assertTrue(all(it["target_model"] == brs.DPO_TARGET for it in self.items))

    def test_no_prompt_selected_without_both_opponents(self) -> None:
        # a selected prompt contributes exactly its 2 opponent items
        by_source = Counter(it["source"] for it in self.items)
        self.assertTrue(all(c == 2 for c in by_source.values()))
        self.assertEqual(len(by_source), 30)  # 30 prompts

    def test_10_complementary_partitions(self) -> None:
        parts = self.partitions
        self.assertEqual(len(parts), 10)                    # C(6,3)/2
        for half_a, half_b in parts:
            self.assertEqual(len(half_a), 3)
            self.assertEqual(len(half_b), 3)
            self.assertEqual(set(half_a) | set(half_b), set(range(6)))   # a partition
            self.assertEqual(set(half_a) & set(half_b), set())          # disjoint

    def test_each_rater_has_exactly_30(self) -> None:
        for r in range(brs.N_RATERS):
            self.assertEqual(len(self.rater_items[r]), brs.QUESTIONS_PER_RATER)

    def test_each_item_gets_exactly_3_labels(self) -> None:
        self.assertEqual(len(self.item_trio), brs.N_ITEMS)  # all 60 covered
        self.assertTrue(all(len(t) == brs.LABELS_PER_ITEM for t in self.item_trio.values()))

    def test_no_rater_sees_a_prompt_twice(self) -> None:
        # the bug the mentor caught: a rater must never get both opponent-items
        # of one prompt.
        for r in range(brs.N_RATERS):
            sources = [it["source"] for it in self.rater_items[r]]
            self.assertEqual(len(sources), len(set(sources)),
                             f"rater {r} sees a prompt more than once")

    def test_each_rater_sees_both_opponents(self) -> None:
        for r in range(brs.N_RATERS):
            opps = {it["opponent_model"] for it in self.rater_items[r]}
            self.assertEqual(len(opps), 2, f"rater {r} sees only one opponent")

    def test_total_labels(self) -> None:
        total = sum(len(self.rater_items[r]) for r in range(brs.N_RATERS))
        self.assertEqual(total, brs.N_ITEMS * brs.LABELS_PER_ITEM)  # 60 × 3 = 180


if __name__ == "__main__":
    unittest.main()
