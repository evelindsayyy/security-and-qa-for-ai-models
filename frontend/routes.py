"""
flask routes for the draft nutrition-label frontend.

Most pages load json/jsonl from pipeline output on disk. Eval, scan, and
safety pillars also support browser-launched runs (subprocess + polling).
"""

from __future__ import annotations

from flask import render_template

from gateway.catalog import get_gateway_catalog


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
    safety_worst_pass_rate = None
    safety_worst_tier = "—"
    benchmark_has = False
    benchmark_count = 0

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
            safety_worst_pass_rate = saf["models"][0]["summary_pass_rate"]
            safety_worst_tier = saf["models"][0]["tier"]
    except Exception:
        pass

    try:
        from frontend.benchmark_data import get_benchmarks_data

        bench = get_benchmarks_data()
        benchmark_has = bench["has_runs"]
        benchmark_count = len(bench["runs"])
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
        "safety_worst_pass_rate": safety_worst_pass_rate,
        "safety_worst_tier": safety_worst_tier,
        "benchmark_has": benchmark_has,
        "benchmark_count": benchmark_count,
    }


def register_routes(app):
    @app.route("/")
    def index():
        return render_template("index.html", **_hub_context())

    @app.route("/scans")
    def scans():
        from frontend.scan_data import get_scans_data

        return render_template("scans.html", **get_scans_data())

    @app.route("/scans/new")
    def scan_run_new():
        from frontend.scan_launch import get_launch_options

        return render_template("scan_run_new.html", **get_launch_options())

    @app.route("/scans/start", methods=["POST"])
    def scan_run_start():
        from flask import redirect, request, url_for

        from frontend.scan_launch import start_run, validate_launch

        hf_repo = request.form.get("hf_repo", "")
        error = validate_launch(
            hf_repo,
            skip_modelscan=not request.form.get("run_modelscan"),
            skip_fickling=not request.form.get("run_fickling"),
            skip_modelaudit=not request.form.get("run_modelaudit"),
            skip_deps=not request.form.get("run_deps"),
            skip_secrets=not request.form.get("run_secrets"),
        )
        if error:
            return error, 400
        slug, _already = start_run(
            hf_repo,
            skip_modelscan=not request.form.get("run_modelscan"),
            skip_fickling=not request.form.get("run_fickling"),
            skip_modelaudit=not request.form.get("run_modelaudit"),
            skip_deps=not request.form.get("run_deps"),
            skip_secrets=not request.form.get("run_secrets"),
        )
        return redirect(url_for("scan_detail", slug=slug, status="running"))

    @app.route("/scans/<slug>/status")
    def scan_run_status(slug: str):
        from flask import jsonify

        from frontend.scan_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/scans/<slug>")
    def scan_detail(slug: str):
        from flask import request

        from frontend.scan_data import get_scan_detail

        detail = get_scan_detail(slug)
        if detail is None or request.args.get("status") == "running":
            from frontend.scan_launch import get_status

            status = get_status(slug)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "scan_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                )

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

    @app.route("/eval-run/start-custom", methods=["POST"])
    def eval_run_start_custom():
        from flask import redirect, request, url_for

        from frontend.eval_launch import (
            start_run,
            validate_custom_questions,
            validate_launch,
            write_custom_suite,
        )

        candidate = request.form.get("candidate", "")
        judge = request.form.get("judge", "")
        try:
            max_tokens = int(request.form.get("max_tokens", ""))
        except ValueError:
            return "max_tokens must be an integer", 400

        # Validate the user's pasted questions as data before anything touches
        # the filesystem or a subprocess (the custom-content security boundary).
        questions, q_error = validate_custom_questions(request.form.get("questions", ""))
        if q_error is not None:
            return f"custom questions: {q_error}", 400

        suite_key = write_custom_suite(questions)
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

    @app.route("/benchmarks/new")
    def benchmark_run_new():
        from frontend.benchmark_launch import get_launch_options

        return render_template("benchmark_run_new.html", **get_launch_options())

    @app.route("/benchmarks/start", methods=["POST"])
    def benchmark_run_start():
        from flask import redirect, request, url_for

        from frontend.benchmark_launch import start_run, validate_launch

        benchmark_key = request.form.get("benchmark", "")
        model = request.form.get("model", "")
        error = validate_launch(benchmark_key, model)
        if error:
            return error, 400
        slug, _already = start_run(benchmark_key, model)
        return redirect(url_for("benchmark_detail", slug=slug, status="running"))

    @app.route("/benchmarks/<slug>/status")
    def benchmark_run_status(slug: str):
        from flask import jsonify

        from frontend.benchmark_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/benchmarks/<slug>")
    def benchmark_detail(slug: str):
        from flask import request

        from frontend.benchmark_data import get_benchmark_detail

        detail = get_benchmark_detail(slug)
        if detail is None or request.args.get("status") == "running":
            from frontend.benchmark_launch import get_status

            status = get_status(slug)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "benchmark_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                )

        if detail is None:
            return render_template(
                "benchmark_detail.html",
                missing=True,
                slug=slug,
            )
        return render_template("benchmark_detail.html", missing=False, **detail)

    @app.route("/safety")
    def safety():
        from frontend.safety_data import get_safety_data

        return render_template("safety.html", **get_safety_data())

    @app.route("/safety/new")
    def safety_run_new():
        from frontend.safety_launch import get_launch_options

        return render_template("safety_run_new.html", **get_launch_options())

    @app.route("/safety/start", methods=["POST"])
    def safety_run_start():
        from flask import redirect, request, url_for

        from frontend.safety_launch import start_run, validate_launch

        model = request.form.get("gateway_model", "")
        skip_redteam = request.form.get("skip_redteam") == "on"
        skip_garak = request.form.get("skip_garak") == "on"
        skip_promptfoo = request.form.get("skip_promptfoo") == "on"
        garak_probes = request.form.get("garak_probes", "").strip()
        error = validate_launch(
            model,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes,
        )
        if error:
            return error, 400
        slug, _already = start_run(
            model,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes or None,
        )
        return redirect(url_for("safety_detail", slug=slug, status="running"))

    @app.route("/safety/<slug>/status")
    def safety_run_status(slug: str):
        from flask import jsonify

        from frontend.safety_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/safety/<slug>")
    def safety_detail(slug: str):
        from flask import request

        from frontend.safety_data import get_safety_detail

        detail = get_safety_detail(slug)
        if detail is None or request.args.get("status") == "running":
            from frontend.safety_launch import get_status

            status = get_status(slug)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "safety_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                )

        if detail is None:
            return render_template(
                "safety_detail.html",
                missing=True,
                slug=slug,
            )
        return render_template("safety_detail.html", missing=False, **detail)

    @app.route("/models")
    def models_catalog():
        gw = get_gateway_catalog()
        return render_template(
            "catalog.html",
            gateway=gw["models"],
            gateway_by_category=gw["by_category"],
            gateway_count=gw["count"],
            gateway_source=gw["source"],
            gateway_fetched_at=gw["fetched_at"],
            gateway_error=gw["error"],
            gateway_deprecated=gw["deprecated"],
        )

    @app.route("/models/<slug>")
    def model_detail(slug: str):
        from frontend.eval_run_data import get_model_detail

        detail = get_model_detail(slug)
        if detail is None:
            return render_template("model_detail.html", missing=True, slug=slug)
        return render_template("model_detail.html", missing=False, **detail)

    @app.route("/gateway/refresh", methods=["POST"])
    def gateway_refresh():
        from flask import redirect, request, url_for

        # Force a live re-fetch so the catalog + every launch dropdown picks up
        # new/removed gateway models immediately (instead of waiting for the cache TTL).
        get_gateway_catalog(force_refresh=True)
        return redirect(
            request.form.get("next") or request.referrer or url_for("models_catalog")
        )

    @app.route("/hello")
    def hello():
        return "ok — flask app is running"
