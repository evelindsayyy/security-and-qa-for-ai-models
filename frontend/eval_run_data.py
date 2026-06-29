"""
Data source for the /eval-run comparison page.

Aggregates eval runs into comparison-table rows sorted by overall mean (best
first). Postgres when EFFICACY_DB_DSN is set; artifact fallback otherwise.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from frontend.path_safety import is_safe_slug, resolves_inside

ROOT = Path(__file__).parent.parent
EVALUATOR = ROOT / "evaluator"
RESULTS_DIR = EVALUATOR / "results"

# evaluator/ isn't a package; add it to sys.path so we can import schemas.
sys.path.insert(0, str(EVALUATOR))

from schemas import EvaluationResult  # noqa: E402
from cost_perf import (  # noqa: E402
    BALANCED,
    BUDGET,
    QUALITY_FIRST,
    CostPerfWeights,
    ModelCost,
    score_cohort,
)

# The comparison table reads the rubric "overall" as if on a 0–5 display scale.
# Most dimensions are 1–5 (tone is 1–3) and the overall is a rubric-weighted
# mean, so 5.0 is the right denominator for normalizing quality on the
# dashboard. Documented approximation — see metrics.yaml for the real scales.
QUALITY_SCALE_MAX = 5.0

# Reverse map so the page can name the active weighting (v1 always Balanced;
# the slider UI in a later week will pass other presets / custom weights).
# Keyed by the weight *values* (a tuple), not the preset object: evaluator
# modules get imported both bare (`cost_perf`) and as a package
# (`evaluator.cost_perf`), which are distinct classes, so identity/`==` across
# them is unreliable. The value tuple compares cleanly regardless.
def _weights_key(w: CostPerfWeights) -> tuple[float, float, float]:
    return (w.w_quality, w.w_cost, w.w_latency)


_WEIGHTS_NAME = {
    _weights_key(w): name
    for name, w in (("balanced", BALANCED), ("budget", BUDGET),
                    ("quality_first", QUALITY_FIRST))
}


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

    # Dimensions come from the rows themselves (rubric-driven), not a
    # hardcoded list. dict.fromkeys preserves rubric order.
    dims = list(dict.fromkeys(d for r in rows for d in r.scores))
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
        "suite": first.adaptation.task_suite_version,
        "candidate_model": first.adaptation.candidate_model,
        "judge_model": first.adaptation.judge_model,
        "inference_backend": first.adaptation.inference_backend,
        "n": n,
        "ok": ok,
        "cand_fail": cand_fail,
        "judge_fail": judge_fail,
        "dims": dims,
        "dim_means": dim_means,
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
    # Custom ("bring your own") suites live under tasks/custom/.
    if not suite_path.is_file() and suite_version.startswith("custom_"):
        suite_path = EVALUATOR / "tasks" / "custom" / f"{suite_version}.jsonl"
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


def _get_run_detail_files(slug: str) -> dict | None:
    """Full payload for one results JSONL — per-question rows with rationales.

    Slug is the JSONL filename without the .jsonl extension. Returns None
    if the file is missing or unreadable.
    """
    # slug comes straight from the URL — refuse anything that could
    # traverse outside RESULTS_DIR before touching the filesystem.
    if not is_safe_slug(slug):
        return None
    path = RESULTS_DIR / f"{slug}.jsonl"
    if not resolves_inside(RESULTS_DIR, path) or not path.is_file():
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

    # Dimension columns for the detail table, rubric-ordered union over rows.
    dims = list(dict.fromkeys(d for r in rows for d in r.scores))

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
            "dim_scores": {
                d: (scores[d].score if d in scores else None) for d in dims
            },
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
        "dims": dims,
        "mean_overall": mean_overall,
        "mean_latency_ms": mean_latency,
        "p95_latency_ms": p95_latency,
        "total_cost_usd": round(total_cost, 4),
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "questions": questions_rows,
    }


def _postprocess_runs(runs: list[dict]) -> dict:
    """Shared tail for both data paths (files and DB): dedupe to the latest
    run per (candidate, judge, suite), sort best-first, flag ``is_best``,
    and build the page-level summary fields."""
    # Custom ("bring your own") runs are ad-hoc, not a locked comparable suite —
    # keep them out of the cross-model comparison table (they're still reachable
    # by slug from the launch redirect / detail page).
    runs = [r for r in runs if not str(r.get("suite", "")).startswith("custom_")]
    # Result filenames are timestamped, so the lexicographically-largest
    # filename is newest. This drops superseded runs (e.g. an old
    # "12/12 empty" row that a fresh run already fixed) instead of showing both.
    latest: dict[tuple, dict] = {}
    for r in sorted(runs, key=lambda r: r["filename"]):
        latest[(r["candidate_model"], r["judge_model"], r["suite"])] = r
    runs = list(latest.values())
    for r in runs:
        r["model_slug"] = model_slug(r["candidate_model"])  # for /models/<slug>

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
    # Union of dimension columns across runs, preserving per-run rubric order,
    # so the comparison table can render runs from different rubrics together.
    dim_columns = list(dict.fromkeys(d for r in runs for d in r["dims"]))
    return {
        "has_runs": bool(runs),
        "results_dir": str(RESULTS_DIR),
        "runs": runs,
        "dim_columns": dim_columns,
        "judge_summary": " · ".join(judges) if judges else "",
        "n_summary": "/".join(str(n) for n in suite_ns) if suite_ns else "",
    }


def _get_runs_data_files() -> dict:
    """Comparison data: aggregate every results JSONL in the evaluator output dir."""
    if not RESULTS_DIR.exists():
        return {"has_runs": False, "results_dir": str(RESULTS_DIR), "runs": []}
    files = [p for p in RESULTS_DIR.glob("*.jsonl") if "_trace" not in p.name]
    runs = [r for r in (_aggregate_file(p) for p in files) if r is not None]
    return _postprocess_runs(runs)


def model_slug(name: str) -> str:
    """URL-safe slug for a gateway model id ('GPT 4.1 Mini' → 'GPT-4.1-Mini').

    Mirrors evaluator/runner._safe_slug without importing the (heavy) runner
    module. Many-to-one in theory, unique across our model set in practice.
    """
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)


def get_model_detail(slug: str) -> dict | None:
    """Per-model nutrition label: one model's eval runs across every suite.

    Reuses the dispatched ``get_runs_data()`` (DB when available, files
    otherwise), so this works on both paths. Returns None if no run matches.
    """
    if not is_safe_slug(slug):
        return None
    runs = [r for r in get_runs_data()["runs"] if model_slug(r["candidate_model"]) == slug]
    if not runs:
        return None
    runs.sort(key=lambda r: (r["suite"], r["judge_model"]))
    dim_columns = list(dict.fromkeys(d for r in runs for d in r["dims"]))
    overalls = [r["overall"] for r in runs if r["overall"] is not None]
    return {
        "slug": slug,
        "model": runs[0]["candidate_model"],
        "runs": runs,
        "dim_columns": dim_columns,
        "n_runs": len(runs),
        "suites": sorted({r["suite"] for r in runs}),
        "best_overall": max(overalls) if overalls else None,
        "total_cost_usd": sum(r["total_cost_usd"] for r in runs),
    }


def attach_cost_perf(data: dict, weights: CostPerfWeights = BALANCED) -> dict:
    """Enrich comparison runs with cost-vs-performance metrics, then return data.

    Models are scored *per suite* so the cohort normalization compares
    like-for-like (an it_support overall isn't normalized against a SQL one).
    Each scorable run gains a ``cost_perf`` dict (quality-per-$, weighted
    utility, and the normalized components — never one hidden number); runs with
    no overall score get ``cost_perf = None``. A page-level ``cost_perf_weights``
    records the active weighting so the template can show it.

    Works on both run shapes (file + DB) via .get with defaults; mutates in
    place and returns the same dict for convenient chaining.
    """
    runs = data.get("runs", [])
    by_suite: dict[str, list[dict]] = {}
    for r in runs:
        r.setdefault("cost_perf", None)
        by_suite.setdefault(r.get("suite", ""), []).append(r)

    for group in by_suite.values():
        cohort: list[ModelCost] = []
        scorable: list[dict] = []
        for r in group:
            overall = r.get("overall")
            n = r.get("n") or 0
            if overall is None or n <= 0:
                continue  # leaves cost_perf = None
            cohort.append(ModelCost(
                model=r.get("candidate_model", ""),
                quality_overall=overall,
                quality_scale_max=QUALITY_SCALE_MAX,
                cost_per_response_usd=(r.get("total_cost_usd") or 0.0) / n,
                latency_ms=r.get("mean_latency_ms") or 0,
                inference_backend=r.get("inference_backend", "gateway"),
            ))
            scorable.append(r)

        for r, s in zip(scorable, score_cohort(cohort, weights)):
            r["cost_perf"] = {
                "quality_per_dollar": s.quality_per_dollar,
                "utility": s.utility,
                "quality_norm": s.quality_norm,
                "cost_norm": s.cost_norm,
                "latency_norm": s.latency_norm,
                "cost_per_response_usd": s.cost_per_response_usd,
                "note": s.notes[0] if s.notes else "",
            }

    data["cost_perf_weights"] = {
        "preset": _WEIGHTS_NAME.get(_weights_key(weights), "custom"),
        "w_quality": weights.w_quality,
        "w_cost": weights.w_cost,
        "w_latency": weights.w_latency,
    }
    return data


# Public entry points — Postgres when configured, artifact fallback otherwise.


def get_runs_data() -> dict:
    try:
        from frontend import eval_db_data

        if eval_db_data.available():
            return attach_cost_perf(eval_db_data.get_runs_data_db())
    except Exception:
        pass  # any DB hiccup -> files, never a broken page
    return attach_cost_perf(_get_runs_data_files())


def get_run_detail(slug: str) -> dict | None:
    try:
        from frontend import eval_db_data

        if eval_db_data.available():
            detail = eval_db_data.get_run_detail_db(slug)
            if detail is not None:
                return detail
            # slug not loaded into the DB yet (e.g. a just-finished run) —
            # fall through to the file.
    except Exception:
        pass
    return _get_run_detail_files(slug)


_EVAL_ARTIFACT_SUFFIXES = (".jsonl", ".log", "_trace.jsonl")


def delete_eval_run_paths(slug: str) -> list[str]:
    if not is_safe_slug(slug):
        return []
    return [f"evaluator/results/{slug}{suffix}" for suffix in _EVAL_ARTIFACT_SUFFIXES]


def delete_eval_run(slug: str) -> str | None:
    """Remove eval run artifacts (and DB row when configured). Returns error or None."""
    from frontend.eval_launch import is_eval_run_in_progress

    if not is_safe_slug(slug):
        return f"invalid slug: {slug!r}"
    if is_eval_run_in_progress(slug):
        return "cannot delete while the run is still in progress"

    removed_files = 0
    for suffix in _EVAL_ARTIFACT_SUFFIXES:
        path = RESULTS_DIR / f"{slug}{suffix}"
        if path.is_file():
            try:
                path.unlink()
                removed_files += 1
            except OSError as exc:
                return f"could not delete {path.name}: {exc}"

    removed_db = False
    try:
        from frontend import eval_db_data

        if eval_db_data.available():
            removed_db = eval_db_data.delete_run(slug)
    except Exception:
        pass

    if removed_files == 0 and not removed_db:
        return f"no eval run found for slug {slug!r}"
    return None
