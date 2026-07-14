"""
compare_judges.py — judge-comparison tooling, not part of the production pipeline.

Two modes:

1. Live single-question probe (default, week-3 original): runs two judge
   models on the same (question, reference, candidate_response) tuple and
   prints scores + rationales side-by-side.

       cd evaluator && python compare_judges.py

2. From-results analysis (week-4 Thursday): reads every results JSONL on
   disk and computes the decision-relevant cross-judge statistics —
   per-judge candidate rankings, pairwise mean deltas, rank concordance
   (do judges ORDER candidates the same?), leniency, and discrimination
   (strong-weak gap). This is what the interim judge selection is based
   on; the weeks-7-8 validation study (human raters, Pearson + Kappa)
   remains the final arbiter.

       cd evaluator && python compare_judges.py --from-results --suite it_support_v1
"""

from __future__ import annotations

import argparse
import json
import statistics
from itertools import combinations
from pathlib import Path

from candidate import generate_candidate
from judge import judge_response, resolve_rubric


# Current judge pool (Llama 3.3 retired — leniency ceiling; see docs/judge-selection.md).
JUDGES_TO_COMPARE = ("Llama 4 Maverick", "gpt-oss-120b")
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


# ---------------------------------------------------------------------------
# From-results analysis (week 4 Thursday) — pure functions + a report printer
# ---------------------------------------------------------------------------


def load_result_entries(results_dir: Path) -> list[dict]:
    """One summary dict per results JSONL: who judged whom on what, and the
    mean overall. Skips trace files and anything unparsable."""
    entries: list[dict] = []
    for path in sorted(results_dir.glob("*.jsonl")):
        if "_trace" in path.name:
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (OSError, json.JSONDecodeError):
            continue
        if not rows:
            continue
        adaptation = rows[0]["adaptation"]
        overalls = [r["overall"] for r in rows if r.get("overall") is not None]
        if not overalls:
            continue
        entries.append({
            "file": path.name,
            "timestamp": rows[0]["timestamp"],
            "suite": adaptation["task_suite_version"],
            "candidate": adaptation["candidate_model"],
            "judge": adaptation["judge_model"],
            "judge_prompt": adaptation["judge_prompt_version"],
            "n": len(rows),
            "n_scored": len(overalls),
            "mean_overall": statistics.mean(overalls),
        })
    return entries


def latest_per_combo(entries: list[dict]) -> list[dict]:
    """Keep only the newest entry per (suite, candidate, judge) — older runs
    of the same combo are superseded (e.g. pre-bugfix reruns)."""
    best: dict[tuple, dict] = {}
    for e in sorted(entries, key=lambda e: e["timestamp"]):
        best[(e["suite"], e["candidate"], e["judge"])] = e
    return list(best.values())


def judge_agreement(entries: list[dict], suite: str) -> dict:
    """Cross-judge statistics for one suite.

    Returns:
        by_judge:  {judge: {candidate: mean_overall}}
        ranking:   {judge: [candidates best-first]}
        discrimination: {judge: strongest-weakest gap} (None if <2 candidates)
        pairwise:  per judge pair on shared candidates — mean delta (a-b),
                   mean |delta|, and rank concordance: the fraction of shared
                   candidate PAIRS both judges order the same way. 1.0 means
                   judge choice never changes a ranking conclusion.
    """
    pool = [e for e in latest_per_combo(entries) if e["suite"] == suite]
    judges = sorted({e["judge"] for e in pool})
    by_judge = {
        j: {e["candidate"]: e["mean_overall"] for e in pool if e["judge"] == j}
        for j in judges
    }
    ranking = {
        j: sorted(scores, key=lambda c: scores[c], reverse=True)
        for j, scores in by_judge.items()
    }
    discrimination = {
        j: (max(s.values()) - min(s.values()) if len(s) >= 2 else None)
        for j, s in by_judge.items()
    }
    pairwise = []
    for a, b in combinations(judges, 2):
        shared = sorted(set(by_judge[a]) & set(by_judge[b]))
        if not shared:
            continue
        deltas = [by_judge[a][c] - by_judge[b][c] for c in shared]
        pairs = list(combinations(shared, 2))
        concordant = sum(
            1 for c1, c2 in pairs
            if (by_judge[a][c1] - by_judge[a][c2])
            * (by_judge[b][c1] - by_judge[b][c2]) > 0
        )
        pairwise.append({
            "a": a,
            "b": b,
            "shared": shared,
            "mean_delta": statistics.mean(deltas),
            "mean_abs_delta": statistics.mean(abs(d) for d in deltas),
            "rank_concordance": (concordant / len(pairs)) if pairs else None,
        })
    return {
        "suite": suite,
        "judges": judges,
        "by_judge": by_judge,
        "ranking": ranking,
        "discrimination": discrimination,
        "pairwise": pairwise,
    }


def report_from_results(results_dir: Path, suite: str) -> None:
    entries = load_result_entries(results_dir)
    stats = judge_agreement(entries, suite)
    if not stats["judges"]:
        print(f"No scored runs found for suite {suite!r} in {results_dir}")
        return

    print(f"=== Cross-judge analysis: suite {suite} ===")
    print()
    candidates = sorted({c for s in stats["by_judge"].values() for c in s})
    header = f"{'judge':18s}" + "".join(f"{c[:16]:>18s}" for c in candidates) \
        + f"{'discrim.':>10s}"
    print(header)
    print("-" * len(header))
    for j in stats["judges"]:
        scores = stats["by_judge"][j]
        cells = "".join(
            f"{scores[c]:>18.2f}" if c in scores else f"{'—':>18s}"
            for c in candidates
        )
        d = stats["discrimination"][j]
        print(f"{j:18s}{cells}{d:>10.2f}" if d is not None else f"{j:18s}{cells}{'—':>10s}")

    print()
    print("Rankings (best first):")
    for j in stats["judges"]:
        print(f"  {j:18s} {'  >  '.join(stats['ranking'][j])}")

    print()
    print("Pairwise agreement on shared candidates:")
    for p in stats["pairwise"]:
        conc = (
            f"{p['rank_concordance']:.0%}" if p["rank_concordance"] is not None
            else "n/a (<2 shared)"
        )
        print(
            f"  {p['a']} vs {p['b']}:  shared={len(p['shared'])}  "
            f"mean Δ={p['mean_delta']:+.2f}  mean |Δ|={p['mean_abs_delta']:.2f}  "
            f"rank concordance={conc}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Judge comparison tooling.")
    parser.add_argument("--from-results", action="store_true",
                        help="analyze existing results JSONLs instead of "
                             "running the live single-question probe")
    parser.add_argument("--suite", default="it_support_v1",
                        help="suite version to analyze (from-results mode)")
    args = parser.parse_args()
    if args.from_results:
        report_from_results(Path(__file__).parent / "results", args.suite)
    else:
        main()
