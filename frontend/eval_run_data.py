"""
Data source for the /eval-run comparison page. Scans evaluator/results/
for all results JSONL files (skipping _trace files), aggregates each,
and returns a list of per-run rows sorted by overall mean (best first).

Detects the "empty candidate response" artifact (e.g. reasoning models
hitting max_tokens on hidden tokens) and annotates the row with a note
so the table makes the gotcha visible instead of hiding it under a
plausible-looking score.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
EVALUATOR = ROOT / "evaluator"
RESULTS_DIR = EVALUATOR / "results"

# evaluator/ isn't a package; reuse the sys.path trick eval_demo_data uses.
sys.path.insert(0, str(EVALUATOR))

from schemas import EvaluationResult  # noqa: E402


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _aggregate_file(path: Path) -> dict | None:
    """Read one results JSONL and return aggregate metrics. None on parse error."""
    try:
        with path.open("r", encoding="utf-8") as f:
            rows = [
                EvaluationResult.from_dict(json.loads(line))
                for line in f
                if line.strip()
            ]
    except Exception:
        return None
    if not rows:
        return None

    n = len(rows)
    first = rows[0]
    ok = sum(1 for r in rows if not r.candidate_failed and not r.judge_failed)
    cand_fail = sum(1 for r in rows if r.candidate_failed)
    judge_fail = sum(1 for r in rows if r.judge_failed)

    dims = ("accuracy", "completeness", "policy_adherence", "tone")
    dim_means: dict[str, float | None] = {}
    for d in dims:
        vals = [r.scores[d].score for r in rows if d in r.scores]
        dim_means[d] = statistics.mean(vals) if vals else None

    overall_vals = [r.overall for r in rows if r.overall is not None]
    overall_mean = statistics.mean(overall_vals) if overall_vals else None

    latencies = [r.operational.latency_ms for r in rows]
    mean_latency = statistics.mean(latencies)
    p95_latency = _percentile(latencies, 95)

    total_cost = sum(r.operational.estimated_cost_usd for r in rows)

    # Artifact detection: rows where the candidate emitted no visible text.
    # Surfaces the reasoning-model-eats-max_tokens gotcha right in the table.
    empty_count = sum(1 for r in rows if not (r.candidate_response or "").strip())
    note = f"⚠ {empty_count}/{n} empty" if empty_count > 0 else ""

    return {
        "filename": path.name,
        "timestamp": first.timestamp,
        "candidate_model": first.adaptation.candidate_model,
        "judge_model": first.adaptation.judge_model,
        "n": n,
        "ok": ok,
        "cand_fail": cand_fail,
        "judge_fail": judge_fail,
        "accuracy": dim_means["accuracy"],
        "completeness": dim_means["completeness"],
        "policy": dim_means["policy_adherence"],
        "tone": dim_means["tone"],
        "overall": overall_mean,
        "mean_latency_ms": int(mean_latency),
        "p95_latency_ms": int(p95_latency),
        "total_cost_usd": total_cost,
        "note": note,
    }


def get_runs_data() -> dict:
    """Return per-run aggregates for every results JSONL in RESULTS_DIR.

    Adds an ``is_best`` flag to the highest-overall run that has no artifact
    note, so the template can highlight the row that's actually best.
    """
    if not RESULTS_DIR.exists():
        return {"has_runs": False, "results_dir": str(RESULTS_DIR), "runs": []}
    files = [p for p in RESULTS_DIR.glob("*.jsonl") if "_trace" not in p.name]
    runs = [r for r in (_aggregate_file(p) for p in files) if r is not None]
    # Best first by overall mean; None sinks to bottom.
    runs.sort(key=lambda r: (r["overall"] or 0), reverse=True)
    for r in runs:
        r["is_best"] = False
    for r in runs:
        if not r["note"]:
            r["is_best"] = True
            break

    # Page-level summary fields the template can show in the subtitle.
    judges = sorted({r["judge_model"] for r in runs})
    suite_ns = sorted({r["n"] for r in runs})
    return {
        "has_runs": bool(runs),
        "results_dir": str(RESULTS_DIR),
        "runs": runs,
        "judge_summary": " · ".join(judges) if judges else "",
        "n_summary": "/".join(str(n) for n in suite_ns) if suite_ns else "",
    }
