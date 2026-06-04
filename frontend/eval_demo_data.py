"""
Data source for the /eval-demo page. Runs one (question, candidate, judge)
tuple end-to-end through the evaluator pipeline and returns a dict ready
for the template. Reads from the evaluator's file cache, so this is
instant once the smoke tests have populated cache/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# evaluator/ is not a package; add it to sys.path so we can import its modules.
ROOT = Path(__file__).parent.parent
EVALUATOR = ROOT / "evaluator"
sys.path.insert(0, str(EVALUATOR))

from candidate import generate_candidate  # noqa: E402
from judge import judge_response  # noqa: E402


DEMO_QUESTION_INDEX = 1  # line 0 of the JSONL is metadata; line 1 is question 1
CANDIDATE_MODEL = "gpt-5-chat"
JUDGE_MODEL = "Llama 4 Maverick"

# Mirror the rubric's weights/scales so the page can show the overall.
# If the rubric changes, this needs to change too — kept here rather than
# re-parsing the YAML to keep the demo minimal.
_WEIGHTS = {"accuracy": 0.35, "completeness": 0.25, "policy_adherence": 0.30, "tone": 0.10}
_MAX = {"accuracy": 5, "completeness": 5, "policy_adherence": 5, "tone": 3}


def get_demo_data() -> dict:
    rubric_path = EVALUATOR / "tasks" / "rubrics" / "it_support.yaml"
    judge_prompt_path = EVALUATOR / "prompts" / "judge" / "reference_based_v1.txt"
    system_prompt_path = EVALUATOR / "prompts" / "system" / "it_support_v1.txt"
    suite_path = EVALUATOR / "tasks" / "it_support_v1.jsonl"

    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    with suite_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    row = json.loads(lines[DEMO_QUESTION_INDEX])
    question = row["question"]
    reference = row["reference"]

    cand = generate_candidate(
        question=question,
        model=CANDIDATE_MODEL,
        system_prompt=system_prompt,
    )
    verdict = judge_response(
        question=question,
        reference=reference,
        candidate_response=cand.response,
        rubric_path=rubric_path,
        judge_model=JUDGE_MODEL,
        judge_prompt_path=judge_prompt_path,
    )

    overall_display = None
    if not verdict.failed and verdict.scores:
        normalized = sum(
            _WEIGHTS[k] * (verdict.scores[k].score / _MAX[k]) for k in _WEIGHTS
        )
        overall_display = round(normalized * 5, 2)

    return {
        "question": question,
        "reference": reference,
        "candidate_model": CANDIDATE_MODEL,
        "candidate_response": cand.response,
        "candidate_failed": cand.failed,
        "candidate_error": cand.error,
        "latency_ms": cand.latency_ms,
        "prompt_tokens": cand.prompt_tokens,
        "completion_tokens": cand.completion_tokens,
        "judge_model": JUDGE_MODEL,
        "judge_failed": verdict.failed,
        "judge_error": verdict.error,
        "scores": verdict.scores,
        "overall_display": overall_display,
    }
