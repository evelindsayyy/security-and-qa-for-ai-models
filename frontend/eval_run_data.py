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


# Bump to invalidate cached execution sidecars written by an older scorer. v2
# fixes judge-only suites (e.g. it_support) that an early scorer mis-scored as
# all-fail SQL — those stale sidecars are now ignored and recomputed.
_EXEC_CACHE_VERSION = 2


def _execution_summary(path: Path) -> dict | None:
    """Functional pass/fail for an execution (SQL/JSON/numeric) run, cached to a
    ``<slug>_execution.json`` sidecar. None for a judge-scored suite (a suite
    with no execution rows) or any error — the dashboard shows nothing when
    absent. Never raises.

    Lazy + cached: the first view of an execution run runs the checks (fast,
    in-memory) and writes the sidecar; later views read it. The sidecar is
    ``.json`` (not ``.jsonl``) so the runs glob never mistakes it for a run.
    A sidecar from an older scorer version is ignored and recomputed.
    """
    sidecar = path.with_name(f"{path.stem}_execution.json")
    if sidecar.is_file():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            data = None
        # Trust the cache only if it came from the current scorer; otherwise
        # recompute (a stale sidecar may have mis-scored a judge-only suite).
        if isinstance(data, dict) and data.get("cache_version") == _EXEC_CACHE_VERSION:
            return data if data.get("applicable") else None
    try:
        import execution_eval  # lazy: a bad import mustn't break the dashboard

        summary = execution_eval.score_results_file(path)
        # A suite with no execution rows is judge-only, not an execution suite.
        summary["applicable"] = summary.get("n", 0) > 0
    except Exception:
        # scoring failed → cache a marker so we don't re-attempt every page load.
        summary = {"applicable": False}
    summary["cache_version"] = _EXEC_CACHE_VERSION
    try:
        sidecar.write_text(json.dumps(summary), encoding="utf-8")
    except Exception:
        pass
    return summary if summary.get("applicable") else None


def _robustness_summary(rows: list, suite_version: str) -> dict | None:
    """Robustness score-drop for a perturbation-suite run, or None if the suite
    carries no perturbation metadata (every ordinary run). Never raises."""
    try:
        import robustness  # lazy, same reason

        id_to_meta = robustness.suite_id_meta(suite_version)
        if not id_to_meta:
            return None
        raw = [{"question_id": r.question_id, "overall": r.overall} for r in rows]
        report = robustness.robustness_report(raw, id_to_meta)
        if not any(m.get("n") for m in report["by_perturbation"].values()):
            return None
        return report
    except Exception:
        return None


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

    data = {
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
    # Execution accuracy — functional pass-rate, shown only for execution-scored
    # (SQL/JSON/numeric) suites; None for judge-scored runs (the column shows —).
    ex = _execution_summary(path)
    if ex and ex.get("n"):
        data["execution_pass_rate"] = ex["pass_rate"]
        data["execution_passed"] = ex["passed"]
        data["execution_n"] = ex["n"]
    return data


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


def _get_run_detail_files(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict | None:
    """Full payload for one results JSONL — per-question rows with rationales.

    Slug is the JSONL filename without the .jsonl extension (globally unique
    regardless of visibility — eval never nests private output under a
    different directory). Returns None if the file is missing/unreadable, or
    the run's own recorded visibility doesn't match the requested scope
    (the URL the caller resolved to, not the viewer's ambient session).
    """
    from dbutils.run_meta import read_run_meta_for_pillar
    from dbutils.visibility import artifact_visible

    # slug comes straight from the URL — refuse anything that could
    # traverse outside RESULTS_DIR before touching the filesystem.
    if not is_safe_slug(slug):
        return None
    path = RESULTS_DIR / f"{slug}.jsonl"
    if not resolves_inside(RESULTS_DIR, path) or not path.is_file():
        return None
    meta = read_run_meta_for_pillar(RESULTS_DIR / slug, pillar="eval")
    if not artifact_visible(meta, view_mode=visibility, user_id=owner_user_id):
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

    # Execution (functional) scoring for this run, if it's an execution suite —
    # per-question pass/fail shown beside the judge's overall.
    execution = _execution_summary(path)
    exec_by_qid = {row["question_id"]: row for row in (execution or {}).get("rows", [])}

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
        exec_row = exec_by_qid.get(r.question_id)
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
            "exec_passed": exec_row["passed"] if exec_row else None,
            "exec_error": exec_row["error"] if exec_row else None,
            "latency_ms": r.operational.latency_ms,
            "cost_usd": r.operational.estimated_cost_usd,
            "status": status,
            "error": r.error,
        })

    robustness = _robustness_summary(rows, first.adaptation.task_suite_version)

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
        "execution": (
            {"pass_rate": execution["pass_rate"], "passed": execution["passed"],
             "n": execution["n"], "check": execution.get("check")}
            if execution and execution.get("n") else None
        ),
        "robustness": robustness,
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
    from frontend.read_context import artifact_path_visible
    from dbutils import fs_safe

    if not RESULTS_DIR.exists():
        return {"has_runs": False, "results_dir": str(RESULTS_DIR), "runs": []}
    files = [p for p in fs_safe.glob(RESULTS_DIR, "*.jsonl") if "_trace" not in p.name]
    files = [p for p in files if artifact_path_visible(RESULTS_DIR / p.stem, pillar="eval")]
    runs = [r for r in (_aggregate_file(p) for p in files) if r is not None]
    return _postprocess_runs(runs)


def model_slug(name: str) -> str:
    """URL-safe slug for a gateway model id ('GPT 4.1 Mini' → 'GPT-4.1-Mini').

    Mirrors evaluator/runner._safe_slug without importing the (heavy) runner
    module. Many-to-one in theory, unique across our model set in practice.
    """
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in name)


def _is_safe_model_slug(slug: str) -> bool:
    """Traversal-safe validator that also permits an HF ``org/name`` slash.

    ``is_safe_slug`` (filesystem guard) rejects slashes, but model identity for
    self-hosted HF models is genuinely ``org/name`` (e.g. ``qwen/qwen2.5-7b``).
    ``get_model_detail`` only string-compares the slug and does dict lookups —
    no filesystem access — so a single-level slash is safe here as long as we
    still reject path traversal and absolute/backslash paths.
    """
    return (
        bool(slug)
        and ".." not in slug
        and not slug.startswith("/")
        and "\\" not in slug
        and all(c.isalnum() or c in "-_./" for c in slug)
    )


def get_model_detail(slug: str) -> dict | None:
    """Per-model report card: one model's eval runs across every suite.

    Reuses the dispatched ``get_runs_data()`` (DB when available, files
    otherwise), so this works on both paths. Returns None if no run matches.
    """
    if not _is_safe_model_slug(slug):
        return None
    # Resolve either slug convention: the eval-identity form (model_slug,
    # case-preserving) used internally, or the gateway-normalized (lowercase)
    # form the /models catalog links with. Without this, /models/<gateway-slug>
    # finds no eval runs for any mixed-case model (e.g. "GPT 4.1 Mini").
    from frontend.model_identity import gateway_slug

    runs = [
        r for r in get_runs_data()["runs"]
        if slug in (model_slug(r["candidate_model"]), gateway_slug(r["candidate_model"]))
    ]
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


# ---------------------------------------------------------------------------
# Per-model "report card" (the AI Model Advisor label). Joins efficacy with the
# scanner + safety pillars (READ-ONLY) into one at-a-glance view-model. Every
# row is N/A-safe: a pillar with no data for this model renders as "—".
# ---------------------------------------------------------------------------

# /5 efficacy-pill thresholds: green >= OK, amber >= WARN, else red.
_SCORE_OK, _SCORE_WARN = 4.0, 2.5

# tier -> (badge text, css class). Same class vocabulary as the pills.
_TIER_BADGES = {
    "low": ("Low risk", "ok"),
    "medium": ("Medium risk", "warn"),
    "high": ("High risk", "bad"),
    "critical": ("Critical risk", "bad"),
}


def _score_badge(score: float | None) -> dict:
    """A /5 efficacy score -> {value, cls}. None -> N/A."""
    if score is None:
        return {"value": "—", "cls": "na"}
    cls = "ok" if score >= _SCORE_OK else "warn" if score >= _SCORE_WARN else "bad"
    return {"value": f"{score:.2f} / 5", "cls": cls}


def _tier_badge(tier: str | None) -> dict:
    """A scanner/safety severity tier -> {value, cls}. None/unknown -> N/A."""
    if not tier:
        return {"value": "—", "cls": "na"}
    text, cls = _TIER_BADGES.get(str(tier).lower(), (str(tier).title(), "na"))
    return {"value": text, "cls": cls}


def _recommend(it: float | None, qa: float | None, cost_cls: str) -> str:
    """Derive a one-line 'recommended use' from the efficacy + cost signals."""
    scored = [(name, s) for name, s in (("IT support", it), ("Q&A", qa))
              if s is not None]
    if not scored:
        return "—"
    best_name, best_score = max(scored, key=lambda t: t[1])
    if best_score < _SCORE_WARN:
        return "not recommended — low task scores"
    prefix = "cost-sensitive " if cost_cls == "ok" else ""
    return f"{prefix}{best_name}"


def _model_cost_effectiveness(detail: dict) -> float | None:
    """Mean cost-vs-performance utility across the model's scorable runs, on /5."""
    enriched = attach_cost_perf(dict(detail), BALANCED)
    utils = [r["cost_perf"]["utility"] for r in enriched.get("runs", [])
             if r.get("cost_perf")]
    return round(sum(utils) / len(utils) * 5, 2) if utils else None


def _lookup_scan_tier(slug: str) -> str | None:
    """READ-ONLY: this model's file-scan severity tier from the scanner pillar."""
    try:
        from frontend.scan_data import get_scans_data
        for s in get_scans_data().get("scans", []):
            if s.get("slug") == slug:
                return s.get("severity_tier")
    except Exception:  # noqa: BLE001 — the card degrades to N/A, never crashes
        return None
    return None


def _lookup_safety_tier(slug: str) -> str | None:
    """READ-ONLY: this model's red-team safety tier from the safety pillar."""
    try:
        from frontend.safety_data import get_safety_data
        for m in get_safety_data().get("models", []):
            if m.get("slug") == slug:
                return m.get("tier")
    except Exception:  # noqa: BLE001
        return None
    return None


def get_model_card(slug: str) -> dict | None:
    """The per-model label: security (scan + safety) + efficacy + a recommended
    use. Returns None only when the model has no eval runs at all; individual
    rows fall back to N/A."""
    detail = get_model_detail(slug)
    if detail is None:
        return None
    runs = detail["runs"]

    def _suite_overall(suite_key: str) -> float | None:
        vals = [r["overall"] for r in runs
                if r["suite"] == suite_key and r["overall"] is not None]
        return max(vals) if vals else None

    it = _suite_overall("it_support_v1")
    qa = _suite_overall("policy_qa_v1.1")
    cost = _score_badge(_model_cost_effectiveness(detail))

    # ``slug`` is the eval-identity form (model_slug, case-preserving) used to
    # look this model up in the runs. The /models/<slug> detail page keys on the
    # gateway-normalized (lowercase) form, so links must use ``detail_slug`` — a
    # plain model_slug like "GPT-4.1-Mini" would 404 there.
    from frontend.model_identity import gateway_slug

    return {
        "slug": slug,
        "detail_slug": gateway_slug(detail["model"]),
        "model": detail["model"],
        "security": [
            {"label": "File scan", **_tier_badge(_lookup_scan_tier(slug))},
            {"label": "Red-team safety", **_tier_badge(_lookup_safety_tier(slug))},
        ],
        "efficacy": [
            {"label": "IT support tasks", **_score_badge(it)},
            {"label": "General Q&A", **_score_badge(qa)},
            {"label": "Cost Effectiveness", **cost},
        ],
        "recommended_use": _recommend(it, qa, cost["cls"]),
    }


def get_all_model_cards() -> list[dict]:
    """Report cards for every evaluated model, most-recently-evaluated first.

    One card per distinct candidate model that has at least one eval run
    (``get_model_card`` returns None otherwise, so it can't appear). Feeds the
    ``/labels`` gallery. Each card is independently N/A-safe."""
    runs = get_runs_data().get("runs", [])
    # Distinct model slugs, ordered by most recent eval first.
    ordered_slugs: list[str] = []
    seen: set[str] = set()
    for r in sorted(runs, key=lambda r: r.get("timestamp", ""), reverse=True):
        slug = model_slug(r["candidate_model"])
        if slug not in seen:
            seen.add(slug)
            ordered_slugs.append(slug)
    cards = [get_model_card(slug) for slug in ordered_slugs]
    return [c for c in cards if c is not None]


def featured_model_slug() -> str | None:
    """Slug of the most-recently-evaluated model, for the home-page card."""
    runs = get_runs_data().get("runs", [])
    if not runs:
        return None
    latest = max(runs, key=lambda r: r.get("timestamp", ""))
    return model_slug(latest["candidate_model"])


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
                "on_frontier": s.on_frontier,
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
    from frontend import eval_db_data
    from frontend.db_fallback import get_data_with_db_fallback

    data = attach_cost_perf(
        get_data_with_db_fallback(
            eval_db_data.available,
            eval_db_data.get_runs_data_db,
            _get_runs_data_files,
        )
    )
    runs = data.get("runs") or []
    from frontend.staleness import attach_staleness

    attach_staleness(runs, "eval")
    data.update(_build_eval_comparison_section(runs))
    return data


def _eval_matrix_cell(run: dict) -> dict | None:
    overall = run.get("overall")
    if overall is None:
        return None
    return {
        "display": f"{overall:.2f}",
        "score_class": "",
        "slug": run.get("slug"),
    }


def _build_eval_comparison_section(runs: list[dict]) -> dict:
    """Pivot eval runs into suite×model overall matrix."""
    from frontend.eval_launch import SUITES
    from frontend.reference_constants import order_models

    if not runs:
        return {"has_comparison": False, "comparison_models": [], "comparison_rows": []}

    by_suite_model: dict[str, dict[str, dict]] = {}
    for r in runs:
        suite = r.get("suite")
        model = r.get("candidate_model")
        if not suite or not model:
            continue
        bucket = by_suite_model.setdefault(suite, {})
        existing = bucket.get(model)
        if existing is None or (r.get("overall") or 0) > (existing.get("overall") or 0):
            bucket[model] = r

    models_set = {m for per in by_suite_model.values() for m in per}
    comparison_models = order_models(models_set)

    comparison_rows: list[dict] = []
    for suite_key in sorted(set(by_suite_model.keys()) | set(SUITES.keys())):
        label = SUITES.get(suite_key, {}).get("label", suite_key)
        cells: dict[str, dict] = {}
        for model_name in comparison_models:
            row = by_suite_model.get(suite_key, {}).get(model_name)
            if row:
                cell = _eval_matrix_cell(row)
                if cell:
                    cells[model_name] = cell
        comparison_rows.append({
            "key": suite_key,
            "label": label,
            "badge_class": "badge-eval",
            "cells": cells,
        })

    return {
        "has_comparison": bool(comparison_models),
        "comparison_models": comparison_models,
        "comparison_rows": comparison_rows,
    }


def _build_eval_reference_scores(runs: list[dict]) -> dict:
    from frontend.eval_launch import SUITES
    from frontend.reference_constants import PREFERRED_REFERENCE_MODELS

    by_suite_model: dict[str, dict[str, dict]] = {}
    for r in runs:
        suite = r.get("suite")
        model = r.get("candidate_model")
        if not suite or not model or model not in PREFERRED_REFERENCE_MODELS:
            continue
        bucket = by_suite_model.setdefault(suite, {})
        existing = bucket.get(model)
        if existing is None or (r.get("overall") or 0) > (existing.get("overall") or 0):
            bucket[model] = r

    reference_models = list(PREFERRED_REFERENCE_MODELS)
    reference_rows: list[dict] = []
    for suite_key in sorted(set(by_suite_model) | set(SUITES)):
        label = SUITES.get(suite_key, {}).get("label", suite_key)
        cells: dict[str, dict] = {}
        for model_name in reference_models:
            row = by_suite_model.get(suite_key, {}).get(model_name)
            if row:
                cell = _eval_matrix_cell(row)
                if cell:
                    cells[model_name] = cell
        if suite_key in by_suite_model or suite_key in SUITES:
            reference_rows.append({
                "key": suite_key,
                "label": label,
                "badge_class": "badge-eval",
                "cells": cells,
            })

    has_scores = any(c for row in reference_rows for c in row["cells"].values())
    return {
        "has_reference_scores": has_scores,
        "reference_models": reference_models,
        "reference_rows": reference_rows,
    }


def get_run_detail(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict | None:
    """Detail payload for one eval run. Defaults to the public catalog; pass
    ``visibility="private", owner_user_id=...`` for a signed-in user's own copy."""
    try:
        from frontend import eval_db_data

        if eval_db_data.available():
            return eval_db_data.get_run_detail_db(
                slug, visibility=visibility, owner_user_id=owner_user_id
            )
    except Exception:
        pass
    return _get_run_detail_files(slug, visibility=visibility, owner_user_id=owner_user_id)


def get_eval_rerun_params(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict | None:
    """Launch-form prefill from a completed eval run."""
    detail = get_run_detail(slug, visibility=visibility, owner_user_id=owner_user_id)
    if detail is None:
        return None
    return {
        "candidate_model": detail.get("candidate_model"),
        "judge_model": detail.get("judge_model"),
        "suite": detail.get("suite_version") or detail.get("suite"),
    }


_EVAL_ARTIFACT_SUFFIXES = (".jsonl", ".log", "_trace.jsonl")


def delete_eval_run_paths(slug: str) -> list[str]:
    if not is_safe_slug(slug):
        return []
    return [f"evaluator/results/{slug}{suffix}" for suffix in _EVAL_ARTIFACT_SUFFIXES]


def delete_eval_run(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> str | None:
    """Remove eval run artifacts (and DB row when configured). Returns error or None.

    ``visibility``/``owner_user_id`` must match the run's own recorded scope —
    a public-mode delete can't remove another user's private run and vice versa.
    """
    from dbutils.run_meta import read_run_meta_for_pillar
    from dbutils.visibility import artifact_visible
    from frontend.delete_db import db_delete_error
    from frontend.eval_launch import is_eval_run_in_progress

    if not is_safe_slug(slug):
        return f"invalid slug: {slug!r}"

    exists = False
    try:
        from frontend import eval_db_data

        if eval_db_data.available():
            exists = (
                eval_db_data.get_run_detail_db(
                    slug, visibility=visibility, owner_user_id=owner_user_id
                )
                is not None
            )
    except Exception:
        pass
    if not exists:
        meta = read_run_meta_for_pillar(RESULTS_DIR / slug, pillar="eval")
        if not artifact_visible(meta, view_mode=visibility, user_id=owner_user_id):
            return f"no eval run found for slug {slug!r}"
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
    db_available = False
    db_row_existed = False
    db_exc: BaseException | None = None
    try:
        from frontend import eval_db_data

        db_available = eval_db_data.available()
        if db_available:
            try:
                db_row_existed = (
                    eval_db_data.get_run_detail_db(
                        slug, visibility=visibility, owner_user_id=owner_user_id
                    )
                    is not None
                )
            except Exception:
                pass
            try:
                removed_db = eval_db_data.delete_run(
                    slug, visibility=visibility, owner_user_id=owner_user_id
                )
            except Exception as exc:
                db_exc = exc
    except Exception as exc:
        db_exc = exc

    err = db_delete_error(
        db_available=db_available,
        db_row_existed=db_row_existed,
        removed_db=removed_db,
        db_exc=db_exc,
    )
    if err:
        return err

    if removed_files == 0 and not removed_db:
        return f"no eval run found for slug {slug!r}"
    return None


_EVAL_SUITE_ABOUT = {
    "it_support": (
        "Duke IT-support scenarios — troubleshooting, policy Q&A, and ticket-style "
        "requests scored against reference answers."
    ),
    "plain_language": (
        "Plain-language rewriting — dense bureaucratic passages rewritten for a "
        "general audience; faithfulness and clarity weighted in the rubric."
    ),
    "email_drafting": (
        "Professional email drafting — tone, structure, and constraint handling "
        "for Duke-flavored workplace scenarios."
    ),
    "tutoring": (
        "Tutoring scenarios — confused students asking for help; pedagogy and "
        "misconception correction weighted highest."
    ),
    "robustness": (
        "Robustness perturbations — same base questions with typos, informal "
        "phrasing, and ambiguity to measure score stability."
    ),
}


def get_eval_guide_data() -> dict:
    """Rows for the eval reference/guide pages."""
    from frontend.eval_launch import SUITES, suite_question_count

    runs = get_runs_data().get("runs") or []
    example = runs[0] if runs else None
    rows = []
    for key, cfg in SUITES.items():
        rows.append({
            "key": key,
            "label": cfg["label"],
            "badge_class": "badge-eval",
            "about": _EVAL_SUITE_ABOUT.get(key, cfg.get("label", key)),
            "procedure": (
                f"LLM-as-judge scores each of {suite_question_count(key)} questions "
                "against a reference answer using the suite rubric."
            ),
            "scoring": (
                "Per-dimension rubric scores (usually 1–5) roll up to an overall "
                "0–5 headline; higher is better."
            ),
            "default_sample": suite_question_count(key),
            "sample_unit": "questions",
        })
    return {
        "guide_rows": rows,
        "has_example": example is not None,
        "example_slug": example["slug"] if example else None,
        "example_model": example["candidate_model"] if example else None,
        "example_suite": example["suite"] if example else None,
    }


def get_eval_reference_data() -> dict:
    runs = get_runs_data().get("runs") or []
    data = get_eval_guide_data()
    data["has_reference"] = data["has_example"]
    data.update(_build_eval_reference_scores(runs))
    return data
