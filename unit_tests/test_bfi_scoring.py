import unittest

from personality.bfi_scoring import (
    apply_item_score,
    compute_trait_scores,
    reverse_score,
    trait_for_item,
)


class BfiScoringTests(unittest.TestCase):
    def test_reverse_score(self):
        self.assertEqual(reverse_score(1), 5)
        self.assertEqual(reverse_score(5), 1)
        self.assertEqual(reverse_score(3), 3)

    def test_apply_item_score(self):
        self.assertEqual(apply_item_score(4, reverse=False), 4)
        self.assertEqual(apply_item_score(4, reverse=True), 2)
        self.assertIsNone(apply_item_score(9, reverse=False))

    def test_trait_for_item(self):
        traits = {
            "extraversion": {"items": [1, 6]},
            "openness": {"items": [5]},
        }
        self.assertEqual(trait_for_item(1, traits), "extraversion")
        self.assertEqual(trait_for_item(5, traits), "openness")
        self.assertIsNone(trait_for_item(99, traits))

    def test_compute_trait_scores(self):
        traits = {
            "extraversion": {"items": [1, 6]},
            "agreeableness": {"items": [2]},
            "conscientiousness": {"items": [3]},
            "neuroticism": {"items": [4]},
            "openness": {"items": [5]},
        }
        rows = [
            {"trait": "extraversion", "scored": True, "scored_value": 4},
            {"trait": "extraversion", "scored": True, "scored_value": 2},
            {"trait": "agreeableness", "scored": True, "scored_value": 5},
            {"trait": "openness", "scored": False, "scored_value": None},
        ]
        scores = compute_trait_scores(rows, traits=traits)
        self.assertEqual(scores["extraversion"], 3.0)
        self.assertEqual(scores["agreeableness"], 5.0)
        self.assertIsNone(scores["openness"])


if __name__ == "__main__":
    unittest.main()
