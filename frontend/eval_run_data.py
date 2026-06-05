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

# evaluator/ isn't a package; add it to sys.path so we can import schemas.
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
        "slug": path.stem,  # used by /eval-run/<slug>
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


def _truncate(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _load_suite_questions(suite_version: str) -> dict[str, str]:
    """Map question_id -> question text by reading the locked suite JSONL.

    The runner records ``adaptation.task_suite_version`` per row; we use
    that string as the suite filename stem (e.g. 'it_support_v1' →
    'evaluator/tasks/it_support_v1.jsonl'). Empty dict if the file is
    missing — the detail page degrades to id-only.
    """
    suite_path = EVALUATOR / "tasks" / f"{suite_version}.jsonl"
    questions: dict[str, str] = {}
    if not suite_path.is_file():
        return questions
    with suite_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in row and "question" in row:
                questions[row["id"]] = row["question"]
    return questions


def get_run_detail(slug: str) -> dict | None:
    """Full payload for one results JSONL — per-question rows with rationales.

    Slug is the JSONL filename without the .jsonl extension. Returns None
    if the file is missing or unreadable.
    """
    path = RESULTS_DIR / f"{slug}.jsonl"
    if not path.is_file():
        return None
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

    first = rows[0]
    n = len(rows)
    questions_by_id = _load_suite_questions(first.adaptation.task_suite_version)

    # Aggregates — same shape as the comparison row, computed locally so
    # this helper doesn't depend on _aggregate_file's row dict.
    ok = sum(1 for r in rows if not r.candidate_failed and not r.judge_failed)
    cand_fail = sum(1 for r in rows if r.candidate_failed)
    judge_fail = sum(1 for r in rows if r.judge_failed)
    latencies = [r.operational.latency_ms for r in rows]
    mean_latency = int(statistics.mean(latencies)) if latencies else 0
    p95_latency = int(_percentile(latencies, 95))
    total_cost = sum(r.operational.estimated_cost_usd for r in rows)
    total_prompt = sum(r.operational.prompt_tokens for r in rows)
    total_completion = sum(r.operational.completion_tokens for r in rows)
    overall_vals = [r.overall for r in rows if r.overall is not None]
    mean_overall = round(statistics.mean(overall_vals), 2) if overall_vals else None

    # Per-question rows for the detail table.
    questions_rows: list[dict] = []
    for r in rows:
        scores = r.scores
        if r.candidate_failed:
            status = "CAND_FAIL"
        elif r.judge_failed:
            status = "JUDGE_FAIL"
        else:
            status = "OK"
        questions_rows.append({
            "question_id": r.question_id,
            "question": _truncate(questions_by_id.get(r.question_id, ""), 90),
            "candidate_empty": not (r.candidate_response or "").strip(),
            "accuracy": scores["accuracy"].score if "accuracy" in scores else None,
            "completeness": scores["completeness"].score if "completeness" in scores else None,
            "policy": scores["policy_adherence"].score if "policy_adherence" in scores else None,
            "tone": scores["tone"].score if "tone" in scores else None,
            "rationales": {
                dim: scores[dim].rationale for dim in scores
            },
            "overall": r.overall,
            "latency_ms": r.operational.latency_ms,
            "cost_usd": r.operational.estimated_cost_usd,
            "status": status,
            "error": r.error,
        })

    return {
        "slug": slug,
        "filename": path.name,
        "run_id": first.evaluation_run_id,
        "timestamp": first.timestamp,
        "candidate_model": first.adaptation.candidate_model,
        "candidate_model_version": first.adaptation.candidate_model_version,
        "judge_model": first.adaptation.judge_model,
        "suite_version": first.adaptation.task_suite_version,
        "rubric_version": first.adaptation.rubric_version,
        "system_prompt_version": first.adaptation.system_prompt_version,
        "judge_prompt_version": first.adaptation.judge_prompt_version,
        "temperature": first.adaptation.temperature,
        "max_tokens": first.adaptation.max_tokens,
        "n": n,
        "ok": ok,
        "cand_fail": cand_fail,
        "judge_fail": judge_fail,
        "mean_overall": mean_overall,
        "mean_latency_ms": mean_latency,
        "p95_latency_ms": p95_latency,
        "total_cost_usd": round(total_cost, 4),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "questions": questions_rows,
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
