"""
Cross-pillar model endpoints — a row per model with scan + safety + eval +
benchmark data merged (``frontend.model_rollup``), not scoped to one pillar.

Routes (mounted under /api by api.register_api):
    GET  /api/models           every model with data in >=1 pillar
    GET  /api/models/<slug>    full cross-pillar rollup for one model
"""

from __future__ import annotations

from flask import Blueprint

from api.paging import page_rows, parse_paging
from api.responses import err, json_errors, ok
from frontend import model_rollup
from frontend.path_safety import is_safe_slug

bp = Blueprint("models_api", __name__)


@bp.get("/models")
@json_errors
def list_models():
    rows = model_rollup.get_models_union()
    paging, error = parse_paging()
    if error is not None:
        return error
    limit, offset = paging
    page = rows[offset : offset + limit]
    return ok(page, meta=page_rows(rows, limit, offset))


@bp.get("/models/<slug>")
@json_errors
def get_model(slug: str):
    if not is_safe_slug(slug):
        return err("invalid model id", 400)
    rollup = model_rollup.get_model_rollup(slug)
    if rollup is None:
        return err("model not found", 404)
    return ok(rollup)
