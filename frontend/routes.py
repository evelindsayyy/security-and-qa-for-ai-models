"""
flask routes for the draft nutrition-label frontend.

all pages are read-only: they load json/jsonl from scanner/output and
evaluator/results on disk. no subprocess, no api calls yet.

week 5+: routes become thin handlers that call GET /api/... instead.
"""

from __future__ import annotations

from flask import render_template

from frontend.catalog import GATEWAY_MODELS, HF_SCAN_MODELS


def _hub_context() -> dict:
    """build home page counts — never crash if one data dir is missing."""
    scan_count = 0
    scan_worst_tier = "—"
    scan_worst_score = None
    eval_count = 0
    eval_best_overall = None
    eval_has = False
    scan_has = False

    try:
        from frontend.scan_data import get_scans_data

        sd = get_scans_data()
        scan_has = sd["has_scans"]
        scan_count = len(sd["scans"])
        if sd["scans"]:
            scan_worst_tier = sd["scans"][0]["severity_tier"]
            scan_worst_score = sd["scans"][0]["overall_risk_score"]
    except Exception:
        pass

    try:
        from frontend.eval_run_data import get_runs_data

        ed = get_runs_data()
        eval_has = ed["has_runs"]
        eval_count = len(ed["runs"])
        if ed["runs"]:
            eval_best_overall = ed["runs"][0]["overall"]
    except Exception:
        pass

    return {
        "gateway_models": GATEWAY_MODELS,
        "hf_models": HF_SCAN_MODELS,
        "scan_has": scan_has,
        "scan_count": scan_count,
        "scan_worst_tier": scan_worst_tier,
        "scan_worst_score": scan_worst_score,
        "eval_has": eval_has,
        "eval_count": eval_count,
        "eval_best_overall": eval_best_overall,
    }


def register_routes(app):
    @app.route("/")
    def index():
        # hub: three pillars at a glance (safety still pending)
        return render_template("index.html", **_hub_context())

    @app.route("/scans")
    def scans():
        from frontend.scan_data import get_scans_data

        return render_template("scans.html", **get_scans_data())

    @app.route("/scans/<slug>")
    def scan_detail(slug: str):
        from frontend.scan_data import get_scan_detail

        detail = get_scan_detail(slug)
        if detail is None:
            return render_template(
                "scan_detail.html",
                missing=True,
                slug=slug,
            )
        return render_template("scan_detail.html", missing=False, **detail)

    @app.route("/eval-run")
    def eval_run():
        # lazy import — don't load evaluator/openai at app startup
        from frontend.eval_run_data import get_runs_data

        return render_template("eval_run.html", **get_runs_data())

    @app.route("/eval-run/<slug>")
    def eval_run_detail(slug: str):
        from frontend.eval_run_data import get_run_detail

        detail = get_run_detail(slug)
        if detail is None:
            return render_template(
                "eval_run_detail.html",
                missing=True,
                slug=slug,
            )
        return render_template("eval_run_detail.html", missing=False, **detail)

    @app.route("/models")
    def models_catalog():
        # same template pattern as /scans and /eval-run (extends base.html)
        return render_template(
            "catalog.html",
            gateway=GATEWAY_MODELS,
            hf=HF_SCAN_MODELS,
        )

    @app.route("/hello")
    def hello():
        return "ok — flask app is running"
