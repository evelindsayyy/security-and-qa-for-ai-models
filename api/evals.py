"""
Efficacy read/write endpoints (Track B) — thin JSON wrappers over the shared eval
data layer (``frontend.eval_run_data``) and ``frontend.eval_launch``.

Routes (mounted under /api by api.register_api):
    GET  /api/evals            list runs (filters: ?suite=, ?model=)
    GET  /api/evals/<slug>     one run's full detail
    GET  /api/evals/<slug>/status  poll job status
    POST /api/evals            start a run (202 + job_id)

Cross-pillar ``GET /api/models`` and ``GET /api/models/<slug>`` live in
``api/models.py`` (``frontend.model_rollup``), not here.
"""

from __future__ import annotations

from flask import Blueprint, request, url_for

from api.launch_helpers import (
    accepted,
    parse_json_body,
    require_str,
    validation_error,
)
from api.paging import page_rows, parse_paging
from api.responses import err, json_errors, ok
from frontend import eval_launch
from frontend import eval_run_data
from frontend.path_safety import is_safe_slug

bp = Blueprint("evals_api", __name__)


@bp.get("/evals")
@json_errors
def list_evals():
    """Eval runs (same rows as the comparison table), filtered then paged."""
    runs = eval_run_data.get_runs_data()["runs"]
    suite = request.args.get("suite")
    model = request.args.get("model")
    if suite:
        runs = [r for r in runs if r["suite"] == suite]
    if model:
        runs = [
            r
            for r in runs
            if r["candidate_model"] == model
            or eval_run_data.model_slug(r["candidate_model"]) == model
        ]

    paging, error = parse_paging()
    if error is not None:
        return error
    limit, offset = paging
    page = runs[offset : offset + limit]
    return ok(page, meta=page_rows(runs, limit, offset))


@bp.get("/evals/<slug>")
@json_errors
def get_eval(slug: str):
    """One run's full detail payload, or 404 if the slug is unknown."""
    if not is_safe_slug(slug):
        return err("invalid eval id", 400)
    detail = eval_run_data.get_run_detail(slug)
    if detail is None:
        return err("eval not found", 404)
    return ok(detail)


@bp.get("/evals/<slug>/status")
@json_errors
def eval_status(slug: str):
    if not is_safe_slug(slug):
        return err("invalid eval id", 400)
    return ok(eval_launch.get_status(slug))


@bp.post("/evals")
@json_errors
def start_eval():
    body = parse_json_body()
    candidate, cand_err = require_str(body, "candidate")
    if cand_err is not None:
        return cand_err
    judge, judge_err = require_str(body, "judge")
    if judge_err is not None:
        return judge_err
    suite, suite_err = require_str(body, "suite")
    if suite_err is not None:
        return suite_err

    raw_max = body.get("max_tokens", 2000)
    try:
        max_tokens = int(raw_max)
    except (TypeError, ValueError):
        return err("max_tokens must be an integer", 400)

    launch_err = eval_launch.validate_launch(candidate, judge, suite, max_tokens)
    if launch_err is not None:
        return validation_error(launch_err)

    slug, already, _visibility = eval_launch.start_run(candidate, judge, suite, max_tokens)
    return accepted(
        slug,
        url_for("evals_api.eval_status", slug=slug),
        already_running=already,
    )
