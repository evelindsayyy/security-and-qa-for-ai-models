"""Route for the unified model-pipeline view (/pipeline).

Kept separate from frontend/routes.py so the pipeline layer stays self-contained;
registered from frontend/__init__.py alongside the main routes.
"""

from __future__ import annotations

from flask import render_template


def register_pipeline_routes(app):
    @app.route("/pipeline")
    def pipeline_overview():
        from frontend.pipeline import build_overview

        return render_template("pipeline.html", **build_overview())
