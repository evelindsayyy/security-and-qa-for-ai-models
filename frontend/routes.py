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

    @app.route("/eval-run/new")
    def eval_run_new():
        from frontend.eval_launch import get_launch_options

        return render_template("eval_run_new.html", **get_launch_options())

    @app.route("/eval-run/start", methods=["POST"])
    def eval_run_start():
        from flask import redirect, request, url_for

        from frontend.eval_launch import start_run, validate_launch

        candidate = request.form.get("candidate", "")
        judge = request.form.get("judge", "")
        suite_key = request.form.get("suite", "")
        try:
            max_tokens = int(request.form.get("max_tokens", ""))
        except ValueError:
            return "max_tokens must be an integer", 400

        # Allowlist validation is the security boundary — nothing that
        # fails it may reach subprocess (TASK.md hard constraint).
        error = validate_launch(candidate, judge, suite_key, max_tokens)
        if error is not None:
            return error, 400

        slug, _already = start_run(candidate, judge, suite_key, max_tokens)
        return redirect(url_for("eval_run_detail", slug=slug, status="running"))

    @app.route("/eval-run/<slug>/status")
    def eval_run_status(slug: str):
        from flask import jsonify

        from frontend.eval_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/eval-run/<slug>")
    def eval_run_detail(slug: str):
        from flask import request

        from frontend.eval_run_data import get_run_detail

        detail = get_run_detail(slug)

        # Live-run flow: while the runner subprocess is still writing the
        # JSONL, render the progress view instead of "not found"/partial.
        if detail is None or request.args.get("status") == "running":
            from frontend.eval_launch import get_status

            status = get_status(slug)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "eval_run_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                )

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
