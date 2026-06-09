"""
flask routes for the draft nutrition-label frontend.

all pages are read-only: they load json/jsonl from scanner/output and
evaluator/results on disk. no subprocess, no api calls yet.

week 5+: routes become thin handlers that call GET /api/... instead.
"""

from __future__ import annotations

from flask import render_template

from frontend.gateway_catalog import get_gateway_catalog
from frontend.hf_scan_catalog import get_hf_scan_catalog


def _hub_context() -> dict:
    """build home page counts — never crash if one data dir is missing."""
    scan_count = 0
    scan_worst_tier = "—"
    scan_worst_score = None
    eval_count = 0
    eval_best_overall = None
    eval_has = False
    scan_has = False
    safety_has = False
    safety_count = 0
    safety_worst_tier = "—"
    safety_worst_pass_rate = None

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

    try:
        from frontend.safety_data import get_safety_data

        saf = get_safety_data()
        safety_has = saf["has_safety"]
        safety_count = len(saf["models"])
        if saf["models"]:
            safety_worst_tier = saf["models"][0]["safety_tier"]
            safety_worst_pass_rate = saf["models"][0]["summary_pass_rate"]
    except Exception:
        pass

    gw = get_gateway_catalog()
    return {
        "gateway_models": gw["models"],
        "gateway_count": gw["count"],
        "gateway_error": gw["error"],
        "scan_has": scan_has,
        "scan_count": scan_count,
        "scan_worst_tier": scan_worst_tier,
        "scan_worst_score": scan_worst_score,
        "eval_has": eval_has,
        "eval_count": eval_count,
        "eval_best_overall": eval_best_overall,
        "safety_has": safety_has,
        "safety_count": safety_count,
        "safety_worst_tier": safety_worst_tier,
        "safety_worst_pass_rate": safety_worst_pass_rate,
    }


def register_routes(app):
    @app.route("/")
    def index():
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

    @app.route("/benchmarks")
    def benchmarks():
        from frontend.benchmark_data import get_benchmarks_data

        return render_template("benchmarks.html", **get_benchmarks_data())

    @app.route("/safety")
    def safety():
        from frontend.safety_data import get_safety_data

        return render_template("safety.html", **get_safety_data())

    @app.route("/safety/<slug>")
    def safety_detail(slug: str):
        from frontend.safety_data import get_safety_detail

        detail = get_safety_detail(slug)
        if detail is None:
            return render_template(
                "safety_detail.html",
                missing=True,
                slug=slug,
            )
        return render_template("safety_detail.html", missing=False, **detail)

    @app.route("/benchmarks/<slug>")
    def benchmark_detail(slug: str):
        from frontend.benchmark_data import get_benchmark_detail

        detail = get_benchmark_detail(slug)
        if detail is None:
            return render_template(
                "benchmark_detail.html",
                missing=True,
                slug=slug,
            )
        return render_template("benchmark_detail.html", missing=False, **detail)

    @app.route("/models")
    def models_catalog():
        gw = get_gateway_catalog()
        hf = get_hf_scan_catalog()
        return render_template(
            "catalog.html",
            gateway=gw["models"],
            gateway_by_category=gw["by_category"],
            gateway_count=gw["count"],
            gateway_source=gw["source"],
            gateway_fetched_at=gw["fetched_at"],
            gateway_error=gw["error"],
            gateway_deprecated=gw["deprecated"],
            hf=hf["models"],
            hf_count=hf["count"],
            hf_source=hf["source"],
            hf_output_dir=hf["output_dir"],
            hf_error=hf["error"],
        )

    @app.route("/hello")
    def hello():
        return "ok — flask app is running"
