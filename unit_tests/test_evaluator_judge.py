"""
Unit tests for the evaluator's pure functions — no Gateway, no API calls.

Covers:
  - judge._parse_scores      (untrusted judge-output parser)
  - judge.resolve_rubric     (shared-dimension reference resolver)
  - runner._weighted_overall (rubric-weighted aggregation math)
  - candidate/judge cache round-trip, corrupt-entry self-heal
  - candidate empty-response handling (reasoning-token budget artifact)

Run from repo root:
  uv run python -m unittest unit_tests.test_evaluator_judge -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# evaluator/ is not a package (its modules import each other flat), so add
# it to sys.path the same way frontend/eval_run_data.py does.
_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import candidate  # noqa: E402
import judge  # noqa: E402
from candidate import CandidateResult  # noqa: E402
from judge import JudgeResult, _parse_scores, _strip_fences, resolve_rubric  # noqa: E402
from runner import _weighted_overall  # noqa: E402
from schemas import DimensionScore  # noqa: E402


_IT_DIMS = ("accuracy", "completeness", "policy_adherence", "tone")


def _valid_payload(dims: tuple[str, ...] = _IT_DIMS) -> dict:
    return {d: {"score": 4, "rationale": f"{d} ok"} for d in dims}


class ParseScoresTest(unittest.TestCase):
    def test_valid_json_parses_all_dimensions(self) -> None:
        scores = _parse_scores(json.dumps(_valid_payload()))
        self.assertEqual(set(scores), set(_IT_DIMS))
        self.assertEqual(scores["accuracy"].score, 4.0)
        self.assertEqual(scores["tone"].rationale, "tone ok")

    def test_fenced_json_is_tolerated(self) -> None:
        raw = "```json\n" + json.dumps(_valid_payload()) + "\n```"
        scores = _parse_scores(raw)
        self.assertEqual(set(scores), set(_IT_DIMS))

    def test_custom_expected_dims(self) -> None:
        dims = ("accuracy", "citation_precision", "contextualization")
        scores = _parse_scores(json.dumps(_valid_payload(dims)), expected_dims=dims)
        self.assertEqual(set(scores), set(dims))

    def test_missing_dimension_raises(self) -> None:
        payload = _valid_payload()
        del payload["tone"]
        with self.assertRaisesRegex(ValueError, "missing required dimension"):
            _parse_scores(json.dumps(payload))

    def test_unexpected_key_raises(self) -> None:
        payload = _valid_payload()
        payload["vibes"] = {"score": 5, "rationale": "extra"}
        with self.assertRaisesRegex(ValueError, "unexpected key"):
            _parse_scores(json.dumps(payload))

    def test_not_json_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            _parse_scores("the answer was great, 5/5")

    def test_non_object_json_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be an object"):
            _parse_scores("[1, 2, 3]")

    def test_non_dict_dimension_raises(self) -> None:
        payload = _valid_payload()
        payload["accuracy"] = 5
        with self.assertRaisesRegex(ValueError, "must be an object"):
            _parse_scores(json.dumps(payload))

    def test_missing_score_field_raises(self) -> None:
        payload = _valid_payload()
        del payload["accuracy"]["score"]
        with self.assertRaisesRegex(ValueError, "must have 'score' and 'rationale'"):
            _parse_scores(json.dumps(payload))

    def test_non_numeric_score_raises(self) -> None:
        payload = _valid_payload()
        payload["accuracy"]["score"] = "great"
        with self.assertRaisesRegex(ValueError, "not numeric"):
            _parse_scores(json.dumps(payload))

    def test_score_above_scale_is_clamped(self) -> None:
        payload = _valid_payload()
        payload["accuracy"]["score"] = 9  # rubric scale is [1, 5]
        scores = _parse_scores(json.dumps(payload), scales={d: (1, 5) for d in _IT_DIMS})
        self.assertEqual(scores["accuracy"].score, 5.0)

    def test_score_below_scale_is_clamped(self) -> None:
        payload = _valid_payload()
        payload["policy_adherence"]["score"] = -3
        scores = _parse_scores(json.dumps(payload), scales={d: (1, 5) for d in _IT_DIMS})
        self.assertEqual(scores["policy_adherence"].score, 1.0)

    def test_fractional_score_is_rounded_to_int(self) -> None:
        payload = _valid_payload()
        payload["completeness"]["score"] = 3.9
        scores = _parse_scores(json.dumps(payload), scales={d: (1, 5) for d in _IT_DIMS})
        self.assertEqual(scores["completeness"].score, 4.0)

    def test_score_respects_per_dimension_scale(self) -> None:
        # tone is a 1-3 dimension: a 5 must clamp to 3, not 5
        payload = _valid_payload()
        payload["tone"]["score"] = 5
        scores = _parse_scores(
            json.dumps(payload),
            scales={"accuracy": (1, 5), "completeness": (1, 5),
                    "policy_adherence": (1, 5), "tone": (1, 3)})
        self.assertEqual(scores["tone"].score, 3.0)

    def test_no_clamp_when_scales_absent(self) -> None:
        # backward compat: with no scales the score passes through unclamped
        payload = _valid_payload()
        payload["accuracy"]["score"] = 9
        scores = _parse_scores(json.dumps(payload))
        self.assertEqual(scores["accuracy"].score, 9.0)

    def test_judge_cache_key_includes_max_tokens(self) -> None:
        kw = dict(judge_model="m", judge_prompt_version="v1", question="q",
                  candidate_response="r", rubric_version="rv1")
        self.assertNotEqual(
            judge._cache_key(**kw, max_tokens=600),
            judge._cache_key(**kw, max_tokens=2000),
        )

    def test_strip_fences_no_fence_passthrough(self) -> None:
        self.assertEqual(_strip_fences('{"a": 1}'), '{"a": 1}')


class ResolveRubricTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def _write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_real_summarization_rubric_resolves_from_shared(self) -> None:
        # Guards the shipped summarization_v1 rubric: its from:shared
        # dimensions must inline anchors and its weights must sum to 1.0.
        rubric_path = _EVALUATOR / "tasks" / "rubrics" / "summarization_v1.yaml"
        rubric, _ = resolve_rubric(rubric_path)
        dims = rubric["dimensions"]
        self.assertEqual(
            set(dims), {"faithfulness", "coverage", "concision", "tone"}
        )
        # shared definitions were inlined (anchors present on each)
        self.assertTrue(all("anchors" in d for d in dims.values()))
        self.assertAlmostEqual(sum(d["weight"] for d in dims.values()), 1.0)

    def test_inline_rubric_passes_through_unchanged(self) -> None:
        raw = (
            "rubric_version: test_v1\n"
            "dimensions:\n"
            "  accuracy:\n"
            "    scale: [1, 5]\n"
            "    weight: 1.0\n"
        )
        path = self._write("inline.yaml", raw)
        rubric, returned_raw = resolve_rubric(path)
        self.assertEqual(returned_raw, raw)
        self.assertEqual(rubric["dimensions"]["accuracy"]["scale"], [1, 5])

    def test_shared_reference_is_resolved_with_task_overlay(self) -> None:
        self._write(
            "_shared.yaml",
            "dimensions:\n"
            "  accuracy:\n"
            "    definition: shared def\n"
            "    scale: [1, 5]\n"
            "    anchors: {1: bad, 5: good}\n",
        )
        path = self._write(
            "task.yaml",
            "rubric_version: task_v1\n"
            "shared_dimensions_lib: _shared.yaml\n"
            "dimensions:\n"
            "  accuracy:\n"
            "    from: shared\n"
            "    weight: 0.7\n"
            "    task_note: task-specific\n"
            "  tone:\n"
            "    scale: [1, 3]\n"
            "    weight: 0.3\n",
        )
        rubric, raw = resolve_rubric(path)
        acc = rubric["dimensions"]["accuracy"]
        # shared fields inlined, task fields overlaid, 'from' marker dropped
        self.assertEqual(acc["definition"], "shared def")
        self.assertEqual(acc["scale"], [1, 5])
        self.assertEqual(acc["weight"], 0.7)
        self.assertEqual(acc["task_note"], "task-specific")
        self.assertNotIn("from", acc)
        # inline dimension kept verbatim; lib metadata removed
        self.assertEqual(rubric["dimensions"]["tone"]["scale"], [1, 3])
        self.assertNotIn("shared_dimensions_lib", rubric)
        self.assertNotIn("from: shared", raw)

    def test_missing_shared_dimension_raises_keyerror(self) -> None:
        self._write("_shared.yaml", "dimensions: {}\n")
        path = self._write(
            "task.yaml",
            "shared_dimensions_lib: _shared.yaml\n"
            "dimensions:\n"
            "  accuracy:\n"
            "    from: shared\n",
        )
        with self.assertRaises(KeyError):
            resolve_rubric(path)

    def test_missing_shared_lib_file_raises(self) -> None:
        path = self._write(
            "task.yaml",
            "shared_dimensions_lib: _nope.yaml\n"
            "dimensions: {}\n",
        )
        with self.assertRaises(FileNotFoundError):
            resolve_rubric(path)


class WeightedOverallTest(unittest.TestCase):
    RUBRIC = {
        "dimensions": {
            "accuracy": {"scale": [1, 5], "weight": 0.5},
            "tone": {"scale": [1, 3], "weight": 0.5},
        },
        "aggregation": {"display_scale": 5},
    }

    def test_full_scores_compute_weighted_display_value(self) -> None:
        scores = {
            "accuracy": DimensionScore(score=4, rationale=""),
            "tone": DimensionScore(score=3, rationale=""),
        }
        # 0.5 * (4/5) + 0.5 * (3/3) = 0.9 → 4.5 on the 0-5 display scale
        self.assertEqual(_weighted_overall(scores, self.RUBRIC), 4.5)

    def test_missing_dimension_returns_none(self) -> None:
        scores = {"accuracy": DimensionScore(score=4, rationale="")}
        self.assertIsNone(_weighted_overall(scores, self.RUBRIC))

    def test_display_scale_defaults_to_five(self) -> None:
        rubric = {"dimensions": {"accuracy": {"scale": [1, 5], "weight": 1.0}}}
        scores = {"accuracy": DimensionScore(score=5, rationale="")}
        self.assertEqual(_weighted_overall(scores, rubric), 5.0)


class CandidateCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(candidate, "_CACHE_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_round_trip(self) -> None:
        result = CandidateResult(
            response="hello", latency_ms=12, prompt_tokens=3, completion_tokens=4
        )
        candidate._cache_write("k1", result)
        self.assertEqual(candidate._cache_read("k1"), result)

    def test_missing_key_is_miss(self) -> None:
        self.assertIsNone(candidate._cache_read("nope"))

    def test_corrupt_entry_is_miss_and_self_heals(self) -> None:
        path = candidate._cache_path("bad")
        path.write_text('{"response": "trunc', encoding="utf-8")
        self.assertIsNone(candidate._cache_read("bad"))
        self.assertFalse(path.exists())  # corrupt file removed

    def test_stale_shape_entry_is_miss(self) -> None:
        path = candidate._cache_path("stale")
        path.write_text('{"unknown_field": 1}', encoding="utf-8")
        self.assertIsNone(candidate._cache_read("stale"))

    def test_write_leaves_no_temp_files(self) -> None:
        candidate._cache_write(
            "k2", CandidateResult(response="x", latency_ms=1, prompt_tokens=1, completion_tokens=1)
        )
        leftovers = list(Path(self._tmp.name).glob("*.tmp"))
        self.assertEqual(leftovers, [])


def _fake_gateway_client(content: str, completion_tokens: int = 500) -> mock.Mock:
    """A stub OpenAI client whose chat completion returns `content`."""
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=completion_tokens),
    )
    client = mock.Mock()
    client.with_options.return_value = client
    client.chat.completions.create.return_value = resp
    return client


class GenerateCandidateEmptyResponseTest(unittest.TestCase):
    """Reasoning models can spend the whole max_tokens budget on hidden
    thinking and 'succeed' with empty visible text. That must surface as a
    candidate failure (skipping the judge) and must NOT be cached, so a
    re-run with a bigger budget actually retries the call.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(candidate, "_CACHE_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _generate(self, client: mock.Mock):
        with mock.patch.object(candidate, "gateway_client", return_value=client):
            return candidate.generate_candidate(
                question="q",
                model="gpt-5-mini",
                system_prompt="sys",
                max_tokens=500,
            )

    def test_empty_response_is_marked_failed(self) -> None:
        result = self._generate(_fake_gateway_client(""))
        self.assertTrue(result.failed)
        self.assertIn("empty response", result.error or "")
        self.assertIn("500/500", result.error or "")  # budget shown for diagnosis

    def test_whitespace_only_response_is_marked_failed(self) -> None:
        result = self._generate(_fake_gateway_client("   \n  "))
        self.assertTrue(result.failed)

    def test_empty_response_is_not_cached(self) -> None:
        client = _fake_gateway_client("")
        self._generate(client)
        self.assertEqual(list(Path(self._tmp.name).glob("*.json")), [])
        # second call must hit the API again, not a cached empty result
        self._generate(client)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_non_empty_response_still_succeeds_and_caches(self) -> None:
        client = _fake_gateway_client("a real answer", completion_tokens=42)
        result = self._generate(client)
        self.assertFalse(result.failed)
        self.assertEqual(result.response, "a real answer")
        self.assertEqual(len(list(Path(self._tmp.name).glob("*.json"))), 1)

    def test_cache_key_includes_max_tokens(self) -> None:
        base = dict(model="m", system_prompt="s", question="q", temperature=0.2)
        key_500 = candidate._cache_key(**base, max_tokens=500)
        key_2000 = candidate._cache_key(**base, max_tokens=2000)
        self.assertNotEqual(key_500, key_2000)


class JudgeCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(judge, "_CACHE_DIR", Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_round_trip_rebuilds_dimension_scores(self) -> None:
        result = JudgeResult(
            scores={"accuracy": DimensionScore(score=4.0, rationale="good")},
            raw_response="{}",
        )
        judge._cache_write("k1", result)
        cached = judge._cache_read("k1")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.scores["accuracy"], DimensionScore(score=4.0, rationale="good"))
        self.assertFalse(cached.failed)

    def test_corrupt_entry_is_miss_and_self_heals(self) -> None:
        path = judge._cache_path("bad")
        path.write_text("not json at all", encoding="utf-8")
        self.assertIsNone(judge._cache_read("bad"))
        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
