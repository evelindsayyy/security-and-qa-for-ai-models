"""
compare_judges.py — one-off experiment, not part of the production pipeline.

Runs two judge models on the same (question, reference, candidate_response)
tuple and prints scores + rationales side-by-side. Purpose: gauge whether
the judge-model choice meaningfully moves the rubric numbers — relevant to
the methodology question "is Llama 3.3 strong enough to judge GPT-5 outputs,
or does the ceiling effect matter here?"

This is exploration. The weeks-7-8 validation study (human raters vs judge,
Pearson + Cohen's Kappa per dimension) formalizes this question; today is
just a fast first look using the cached candidate response from Monday.

Run:  cd evaluator && python compare_judges.py
"""

from __future__ import annotations

import json
from pathlib import Path

from candidate import generate_candidate
from judge import judge_response, resolve_rubric


JUDGES_TO_COMPARE = ("Llama 3.3", "Llama 4 Maverick")
CANDIDATE_MODEL = "gpt-5-chat"


def main() -> None:
    here = Path(__file__).parent
    rubric_path = here / "tasks" / "rubrics" / "it_support.yaml"
    judge_prompt_path = here / "prompts" / "judge" / "reference_based_v1.txt"
    system_prompt_path = here / "prompts" / "system" / "it_support_v1.txt"
    suite_path = here / "tasks" / "it_support_v1.jsonl"

    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    with suite_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    # Line 0 is the suite metadata; line 1 is question 1.
    row = json.loads(lines[1])
    question = row["question"]
    reference = row["reference"]

    # Candidate response (cached from candidate.py — no API call expected).
    cand = generate_candidate(
        question=question,
        model=CANDIDATE_MODEL,
        system_prompt=system_prompt,
    )
    if cand.failed:
        print(f"Candidate FAILED: {cand.error}")
        return

    # Judge each verdict; first run hits the API, re-runs are cached.
    verdicts = {}
    for judge_model in JUDGES_TO_COMPARE:
        print(f"Judging with {judge_model}...", flush=True)
        verdict = judge_response(
            question=question,
            reference=reference,
            candidate_response=cand.response,
            rubric_path=rubric_path,
            judge_model=judge_model,
            judge_prompt_path=judge_prompt_path,
        )
        if verdict.failed:
            print(f"  {judge_model} FAILED: {verdict.error}")
            print(f"  raw: {verdict.raw_response[:200]}")
            return
        verdicts[judge_model] = verdict

    # --- side-by-side scores -------------------------------------------------
    bar = "=" * 78
    print()
    print(bar)
    print(f"Question:  {question}")
    print(f"Candidate: {CANDIDATE_MODEL}")
    print(bar)

    # Dimensions and max scores come from the rubric itself so this script
    # stays correct when pointed at a rubric with a different dimension set.
    rubric, _ = resolve_rubric(rubric_path)
    dim_blocks = rubric.get("dimensions") or {}
    dims = tuple(dim_blocks.keys())
    max_score = {dim: block["scale"][1] for dim, block in dim_blocks.items()}

    col_w = 20
    header = f"{'dimension':18s}  " + "  ".join(f"{j:>{col_w}s}" for j in JUDGES_TO_COMPARE) + f"  {'delta':>8s}"
    print(header)
    print("-" * len(header))

    total_abs_delta = 0.0
    total_normalized_delta = 0.0

    for dim in dims:
        scores = [verdicts[j].scores[dim].score for j in JUDGES_TO_COMPARE]
        delta = scores[1] - scores[0]  # Maverick - 3.3
        total_abs_delta += abs(delta)
        total_normalized_delta += abs(delta) / max_score[dim]
        row_str = (
            f"{dim:18s}  "
            + "  ".join(f"{s:>{col_w}.1f}" for s in scores)
            + f"  {delta:>+8.1f}"
        )
        print(row_str)
    print("-" * len(header))
    print(f"{'mean |delta|':18s}  {'':>{col_w}s}  {'':>{col_w}s}  {total_abs_delta / len(dims):>+8.2f}")
    print(
        f"{'normalized (0-1)':18s}  {'':>{col_w}s}  {'':>{col_w}s}  "
        f"{total_normalized_delta / len(dims):>+8.3f}"
    )

    # --- rationales per dimension -------------------------------------------
    print()
    print("=== Rationales ===")
    for dim in dims:
        print(f"\n[{dim}]")
        for j in JUDGES_TO_COMPARE:
            ds = verdicts[j].scores[dim]
            print(f"  ({j}, score={ds.score})  {ds.rationale}")


if __name__ == "__main__":
    main()
