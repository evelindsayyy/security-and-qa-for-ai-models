"""
api/health.py — liveness endpoint.

    GET /api/health   -> status, db_available, per-pillar db flags
"""

from __future__ import annotations

from flask import Blueprint

from api.responses import ok

bp = Blueprint("health_api", __name__)


def _pillar_db_flags() -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for name, mod_path in (
        ("scan", "frontend.scan_db_data"),
        ("safety", "frontend.safety_db_data"),
        ("eval", "frontend.eval_db_data"),
        ("benchmark", "frontend.benchmark_db_data"),
    ):
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            flags[name] = bool(mod.available())
        except Exception:
            flags[name] = False
    return flags


@bp.get("/health")
def health():
    """Liveness + whether the Postgres read-path is currently reachable."""
    pillars = _pillar_db_flags()
    return ok(
        {
            "status": "ok",
            "db_available": any(pillars.values()),
            "pillars": pillars,
        }
    )
