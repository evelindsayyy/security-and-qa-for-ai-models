"""
api/ — the JSON REST layer (Flask blueprints) over the pipeline's data.

Blueprints mount under ``/api`` via ``register_api()`` in ``frontend/create_app``.
See docs/architecture.md and api/README.md.
"""

from __future__ import annotations

from flask import Flask

from api.benchmarks import bp as benchmarks_bp
from api.evals import bp as evals_bp
from api.health import bp as health_bp
from api.models import bp as models_bp
from api.safety import bp as safety_bp
from api.scans import bp as scans_bp


def register_api(app: Flask) -> None:
    """Mount every api/ blueprint on the given Flask app (prefix /api)."""
    for bp in (health_bp, evals_bp, scans_bp, safety_bp, benchmarks_bp, models_bp):
        app.register_blueprint(bp, url_prefix="/api")
