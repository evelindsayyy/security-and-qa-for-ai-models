"""
aggregate.py

Summarize a results JSONL produced by runner.py. Reads each row through
EvaluationResult.from_dict and prints a small text-aligned table to
stdout with the metrics TASK.md asks for (per-dimension means, overall
mean, mean latency, total cost, failure rate) plus two from metrics.yaml
that the dashboard will want eventually (p95 latency, total tokens).

CLI:
    python evaluator/aggregate.py results/<ts>_<suite>_<candidate>.jsonl

Output is plain print() — no formatting libraries, no JSON output, no
chart deps. The shape is the point: a human reading this in stdout
should immediately know whether to trust the numbers.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from schemas import EvaluationResult


def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile. p in [0, 100]. Returns 0 on empty."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Summarize a results JSONL.")
    p.add_argument(
        "path",
        type=Path,
        help="results JSONL path (produced by runner.py)",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.path.exists():
        print(f"ERROR: file not found: {args.path}")
        return 1

    with args.path.open("r", encoding="utf-8") as f:
        rows = [
            EvaluationResult.from_dict(json.loads(line))
            for line in f
            if line.strip()
        ]

    if not rows:
        print(f"No rows in {args.path}")
        return 1

    first = rows[0]
    n = len(rows)

    # ---- counts ----
    ok = sum(1 for r in rows if not r.candidate_failed and not r.judge_failed)
    cand_fail = sum(1 for r in rows if r.candidate_failed)
    judge_fail = sum(1 for r in rows if r.judge_failed)
    failure_rate = (cand_fail + judge_fail) / n

    # ---- per-dimension means (only over rows where the dim is present) ----
    # Dimensions come from the rows themselves, not a hardcoded list, so any
    # rubric's dimension set aggregates correctly. dict.fromkeys preserves
    # first-seen order, which matches the rubric's dimension order.
    dims = tuple(dict.fromkeys(dim for r in rows for dim in r.scores))
    dim_means: dict[str, float | None] = {}
    for dim in dims:
        vals = [r.scores[dim].score for r in rows if dim in r.scores]
        dim_means[dim] = statistics.mean(vals) if vals else None

    overall_vals = [r.overall for r in rows if r.overall is not None]
    overall_mean = statistics.mean(overall_vals) if overall_vals else None

    # ---- operational ----
    latencies = [r.operational.latency_ms for r in rows]
    mean_latency = statistics.mean(latencies)
    p95_latency = _percentile(latencies, 95)

    total_prompt = sum(r.operational.prompt_tokens for r in rows)
    total_completion = sum(r.operational.completion_tokens for r in rows)
    total_cost = sum(r.operational.estimated_cost_usd for r in rows)

    # ---- print ----
    print(f"=== Aggregate: {args.path.name} ===")
    print(f"  candidate:   {first.adaptation.candidate_model}")
    print(f"  judge:       {first.adaptation.judge_model}")
    print(f"  suite:       {first.adaptation.task_suite_version}  ({n} rows)")
    print(f"  rubric:      {first.adaptation.rubric_version}")
    print()
    print("Counts:")
    print(f"  OK:                {ok}")
    print(f"  candidate_failed:  {cand_fail}")
    print(f"  judge_failed:      {judge_fail}")
    print(f"  failure_rate:      {failure_rate * 100:.1f}%")
    print()
    print("Per-dimension means:")
    for dim, m in dim_means.items():
        m_str = f"{m:.2f}" if m is not None else "—"
        print(f"  {dim:18s} {m_str}")
    print()
    if overall_mean is not None:
        print(f"Overall mean:        {overall_mean:.2f}")
    else:
        print("Overall mean:        —")
    print()
    print("Operational:")
    print(f"  mean latency:      {mean_latency:.0f} ms")
    print(f"  p95 latency:       {p95_latency:.0f} ms")
    print(f"  total prompt tok:  {total_prompt}")
    print(f"  total compl tok:   {total_completion}")
    print(f"  total cost:        ${total_cost:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
