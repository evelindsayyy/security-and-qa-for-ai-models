"""
Schema 1.1.0 additive change: Adaptation gained inference_backend + hf_repo.

What must hold:
  1. The new fields default (gateway / None) when a caller omits them, so
     existing call sites don't break.
  2. A 1.0.0 adaptation blob (no new keys) still round-trips via from_dict —
     i.e. old result files stay readable after the bump (backward compat).
  3. A 1.1.0 row preserves the provenance through to_dict -> from_dict.

Run from repo root:
  uv run python -m unittest unit_tests.test_schema_provenance -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import schemas  # noqa: E402
from schemas import Adaptation, EvaluationResult  # noqa: E402


def _adaptation_kwargs() -> dict:
    """A complete pre-1.1.0 Adaptation kwargs set (no provenance keys)."""
    return dict(
        candidate_model="Qwen/Qwen2.5-7B-Instruct",
        candidate_model_version="self-hosted http://node:8000/v1",
        system_prompt_version="it_support_v1",
        user_prompt_template_version="raw_question_v1",
        temperature=0.2,
        max_tokens=2000,
        task_suite_version="it_support_v1",
        rubric_version="it_support_v1.1",
        judge_model="Llama 4 Maverick",
        judge_prompt_version="reference_based_v2",
    )


class AdaptationDefaultsTest(unittest.TestCase):
    def test_new_fields_default_when_omitted(self) -> None:
        a = Adaptation(**_adaptation_kwargs())
        self.assertEqual(a.inference_backend, "gateway")
        self.assertIsNone(a.hf_repo)

    def test_fields_are_settable(self) -> None:
        a = Adaptation(
            **_adaptation_kwargs(),
            inference_backend="dcc",
            hf_repo="Qwen/Qwen2.5-7B-Instruct",
        )
        self.assertEqual(a.inference_backend, "dcc")
        self.assertEqual(a.hf_repo, "Qwen/Qwen2.5-7B-Instruct")


class BackwardCompatTest(unittest.TestCase):
    def _row_dict(self, adaptation: dict, schema_version: str) -> dict:
        return dict(
            evaluation_run_id="run-1",
            timestamp="2026-06-17T00:00:00Z",
            question_id="q1",
            suite="it_support",
            schema_version=schema_version,
            adaptation=adaptation,
            candidate_response="ok",
            scores={"accuracy": {"score": 4, "rationale": "r"}},
            overall=4.0,
            operational={"latency_ms": 10, "prompt_tokens": 1,
                         "completion_tokens": 2, "estimated_cost_usd": 0.0},
        )

    def test_old_blob_without_new_keys_still_parses(self) -> None:
        # A pre-1.1.0 row has neither inference_backend nor hf_repo in its
        # adaptation; from_dict must fill the defaults rather than KeyError.
        row = EvaluationResult.from_dict(
            self._row_dict(_adaptation_kwargs(), "1.0.0"))
        self.assertEqual(row.adaptation.inference_backend, "gateway")
        self.assertIsNone(row.adaptation.hf_repo)

    def test_new_row_round_trips(self) -> None:
        new_adapt = {
            **_adaptation_kwargs(),
            "inference_backend": "dcc",
            "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
        }
        row = EvaluationResult.from_dict(
            self._row_dict(new_adapt, schemas.SCHEMA_VERSION))
        again = EvaluationResult.from_dict(row.to_dict())  # full round-trip
        self.assertEqual(again.adaptation.inference_backend, "dcc")
        self.assertEqual(again.adaptation.hf_repo, "Qwen/Qwen2.5-7B-Instruct")


if __name__ == "__main__":
    unittest.main()
