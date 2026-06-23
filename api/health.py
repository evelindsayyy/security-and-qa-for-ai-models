"""
api/health.py — liveness endpoint.

    GET /api/health   -> {"status": "ok", "db_available": <bool>}

A zero-dependency way for a client (or a load balancer / uptime check) to
confirm the API is up *without* hitting the data endpoints, and to see whether
the Postgres read-path is currently active (``db_available=false`` means reads
are being served from result files — the documented fallback, not an error).

Its own blueprint so ``register_api`` mounts two — the multi-blueprint seam the
package was built around.
"""

from __future__ import annotations

from flask import Blueprint

from api.responses import ok
from frontend import eval_db_data

bp = Blueprint("health_api", __name__)


@bp.get("/health")
def health():
    """Liveness + whether the DB read-path is currently reachable."""
    return ok({"status": "ok", "db_available": eval_db_data.available()})
