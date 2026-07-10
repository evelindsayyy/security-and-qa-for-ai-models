"""
Unit tests for the pairwise LLM-judge (Track 1 validation study) — no Gateway.

Covers:
  - judge._parse_pairwise   A / B / tie parsing, fences, synonyms, bad input
  - judge.judge_pairwise    success, cache hit, order-dependent cache, retry, fail
  - run_pairwise_judge      order-combine → system id, position flip → tie

Run from repo root:
  uv run python -m unittest unit_tests.test_pairwise_judge -v
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
_EVALUATOR = _ROOT / "evaluator"
_VSTUDY = _ROOT / "docs" / "validation-study"
sys.path.insert(0, str(_EVALUATOR))
sys.path.insert(0, str(_VSTUDY))

import judge  # noqa: E402
from judge import PairwiseResult, _parse_pairwise, judge_pairwise  # noqa: E402
import run_pairwise_judge as rpj  # noqa: E402

_PROMPT = _EVALUATOR / "prompts" / "judge" / "pairwise_v1.txt"


def _fake_gateway_client(*contents: str) -> mock.Mock:
    """Stub OpenAI client returning `contents` across successive create() calls."""
    resps = [SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=c))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
    ) for c in contents]
    client = mock.Mock()
    client.with_options.return_value = client
    client.chat.completions.create.side_effect = resps
    return client


class ParsePairwiseTest(unittest.TestCase):
    def test_a_b_tie(self) -> None:
        self.assertEqual(_parse_pairwise('{"winner":"A","rationale":"x"}')[0], "A")
        self.assertEqual(_parse_pairwise('{"winner":"B","rationale":"x"}')[0], "B")
        self.assertEqual(_parse_pairwise('{"winner":"tie"}')[0], "tie")

    def test_synonyms_and_case(self) -> None:
        self.assertEqual(_parse_pairwise('{"winner":"Response 1"}')[0], "A")
        self.assertEqual(_parse_pairwise('{"winner":"EQUAL"}')[0], "tie")

    def test_fenced_and_prose_wrapped(self) -> None:
        self.assertEqual(_parse_pairwise('```json\n{"winner":"B"}\n```')[0], "B")
        self.assertEqual(_parse_pairwise('Verdict: {"winner":"A"} .')[0], "A")

    def test_rationale_extracted(self) -> None:
        self.assertEqual(_parse_pairwise('{"winner":"A","rationale":"clearer"}'),
                         ("A", "clearer"))

    def test_bad_input_raises(self) -> None:
        for bad in ("not json", "{}", '{"winner":"maybe"}', '{"rationale":"x"}'):
            with self.assertRaises(ValueError):
                _parse_pairwise(bad)


class JudgePairwiseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = mock.patch.object(judge, "_CACHE_DIR", Path(self._tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def _call(self, a="a", b="b", model="J"):
        return judge_pairwise(question="q", response_a=a, response_b=b,
                              judge_model=model, judge_prompt_path=_PROMPT)

    def test_success(self) -> None:
        with mock.patch.object(judge, "gateway_client",
                               return_value=_fake_gateway_client('{"winner":"A","rationale":"clearer"}')):
            r = self._call()
        self.assertFalse(r.failed)
        self.assertEqual((r.winner, r.rationale), ("A", "clearer"))

    def test_cache_hit_skips_second_call(self) -> None:
        client = _fake_gateway_client('{"winner":"B"}')
        with mock.patch.object(judge, "gateway_client", return_value=client):
            self._call()
            self._call()
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_order_dependent_cache(self) -> None:
        # (a,b) and (b,a) are distinct entries — the swap re-hits the API.
        client = _fake_gateway_client('{"winner":"A"}', '{"winner":"A"}')
        with mock.patch.object(judge, "gateway_client", return_value=client):
            self._call(a="a", b="b")
            self._call(a="b", b="a")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_retry_once_then_parse(self) -> None:
        client = _fake_gateway_client("garbage", '{"winner":"tie"}')
        with mock.patch.object(judge, "gateway_client", return_value=client):
            r = self._call()
        self.assertEqual(r.winner, "tie")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_fails_after_two_bad(self) -> None:
        with mock.patch.object(judge, "gateway_client",
                               return_value=_fake_gateway_client("nope", "still nope")):
            r = self._call()
        self.assertTrue(r.failed)


class DriverCombineTest(unittest.TestCase):
    ITEM = {"item_id": "itm-001", "source": "s", "prompt": "p",
            "target_model": "Qwen", "opponent_model": "GPT", "task_type": "email"}
    RESP = {("s", "Qwen"): "qwen text", ("s", "GPT"): "gpt text"}

    def test_winner_to_system(self) -> None:
        self.assertEqual(rpj._winner_to_system("A", "Qwen", "GPT"), "Qwen")
        self.assertEqual(rpj._winner_to_system("B", "Qwen", "GPT"), "GPT")
        self.assertEqual(rpj._winner_to_system("tie", "Qwen", "GPT"), "tie")

    def _judge_item(self, w1, w2):
        # judge_item calls judge_pairwise twice: order1 then order2 (swapped).
        results = [PairwiseResult(winner=w1), PairwiseResult(winner=w2)]
        with mock.patch.object(judge, "judge_pairwise", side_effect=results):
            return rpj.judge_item(self.ITEM, self.RESP, judge_model="J")

    def test_consistent_winner_maps_to_system(self) -> None:
        # order1 A→Qwen ; order2 B→Qwen  → both say Qwen
        rec = self._judge_item("A", "B")
        self.assertEqual(rec["judge_pref"], "Qwen")
        self.assertFalse(rec["flipped"])

    def test_position_flip_becomes_tie(self) -> None:
        # order1 A→Qwen ; order2 A→GPT  → disagree → tie + flip
        rec = self._judge_item("A", "A")
        self.assertEqual(rec["judge_pref"], "tie")
        self.assertTrue(rec["flipped"])

    def test_explicit_tie_is_preserved(self) -> None:
        rec = self._judge_item("tie", "tie")
        self.assertEqual(rec["judge_pref"], "tie")
        self.assertFalse(rec["flipped"])

    def test_missing_response_returns_none(self) -> None:
        with mock.patch.object(judge, "judge_pairwise"):
            self.assertIsNone(rpj.judge_item(
                {**self.ITEM, "source": "absent"}, self.RESP, judge_model="J"))

    def test_failed_judge_recorded(self) -> None:
        results = [PairwiseResult(failed=True, error="boom"),
                   PairwiseResult(winner="A")]
        with mock.patch.object(judge, "judge_pairwise", side_effect=results):
            rec = rpj.judge_item(self.ITEM, self.RESP, judge_model="J")
        self.assertTrue(rec["failed"])


if __name__ == "__main__":
    unittest.main()
