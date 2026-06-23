"""
Efficacy read endpoints (Track B) — thin JSON wrappers over the shared eval
data layer (``frontend.eval_run_data``), which dispatches to the Postgres
repository (``evaluator/db/queries.py``) when a DB is configured and falls back
to result files otherwise. So the API returns the SAME numbers the dashboard
shows, with or without a database.

Routes (mounted under /api by api.register_api):
    GET /api/evals            list runs (filters: ?suite=, ?model=)
    GET /api/evals/<slug>     one run's full detail
    GET /api/models/<slug>    one model's rollup across suites

NOTE: this imports the data layer that currently lives under ``frontend/``.
That module is pure data (returns dicts, no HTML), so the coupling is to the
data layer, not the UI — relocating it to a neutral package is a later cleanup.
"""

from __future__ import annotations

from flask import Blueprint, request

from api.responses import err, json_errors, ok
from frontend import eval_run_data
from frontend.path_safety import is_safe_slug

bp = Blueprint("evals_api", __name__)

# Pagination: a default page size keeps a large catalog from being returned in
# one payload; the cap bounds what a single request can ask for. ``meta.total``
# still reports the full filtered count so a client knows how many pages exist.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _paging():
    """Parse ?limit / ?offset into a clamped (limit, offset), or an error
    response on bad input. Returns ((limit, offset), None) or (None, err)."""
    raw_limit = request.args.get("limit", DEFAULT_LIMIT)
    raw_offset = request.args.get("offset", 0)
    try:
        limit, offset = int(raw_limit), int(raw_offset)
    except (TypeError, ValueError):
        return None, err("limit and offset must be integers", 400)
    if limit < 0 or offset < 0:
        return None, err("limit and offset must be non-negative", 400)
    return (min(limit, MAX_LIMIT), offset), None


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
        runs = [r for r in runs
                if r["candidate_model"] == model
                or eval_run_data.model_slug(r["candidate_model"]) == model]

    paging, error = _paging()
    if error is not None:
        return error
    limit, offset = paging
    total = len(runs)
    page = runs[offset:offset + limit]
    return ok(page, meta={"total": total, "limit": limit, "offset": offset})


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


@bp.get("/models/<slug>")
@json_errors
def get_model(slug: str):
    """One model's rollup across every suite it was evaluated on."""
    if not is_safe_slug(slug):
        return err("invalid model id", 400)
    detail = eval_run_data.get_model_detail(slug)
    if detail is None:
        return err("model not found", 404)
    return ok(detail)
