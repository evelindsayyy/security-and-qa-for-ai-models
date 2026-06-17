"""
api/ — the JSON REST layer (Flask blueprints) over the pipeline's data.

Today: Track B's efficacy read endpoints (``api/evals.py``). Track A will add
scans/safety blueprints alongside; ``register_api()`` is the single place the
app mounts them, all under the ``/api`` prefix. See docs/architecture.md.
"""

from __future__ import annotations

from flask import Flask

from api.evals import bp as evals_bp


def register_api(app: Flask) -> None:
    """Mount every api/ blueprint on the given Flask app (prefix /api)."""
    app.register_blueprint(evals_bp, url_prefix="/api")
