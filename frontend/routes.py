"""
Flask routes for the nutrition-label frontend.

List and detail pages read pillar results via ``*_data.py`` modules.
Browser-launched runs use subprocess + polling.
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
        slug, already = start_run(
            hf_repo,
            skip_modelscan=not request.form.get("run_modelscan"),
            skip_fickling=not request.form.get("run_fickling"),
            skip_modelaudit=not request.form.get("run_modelaudit"),
            skip_deps=not request.form.get("run_deps"),
            skip_secrets=not request.form.get("run_secrets"),
        )
        status = "reused" if already else "running"
        return redirect(url_for("scan_detail", slug=slug, status=status))

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

    @app.route("/scans/<slug>/delete", methods=["GET", "POST"])
    def scan_delete(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.result_delete import scan_delete_context
        from frontend.scan_data import delete_scan

        if request.method == "GET":
            ctx = scan_delete_context(slug)
            if ctx is None:
                return redirect(url_for("scans"))
            if ctx.get("error"):
                return ctx["error"], 400
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            return "confirmation required", 400
        error = delete_scan(slug)
        if error:
            return error, 400
        return redirect(url_for("scans"))

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

        from frontend.eval_launch import (
            get_launch_options,
            start_run,
            validate_hf_candidate,
            validate_launch,
        )

        # Candidate source: a gateway model (runs now) or a Hugging Face model
        # (validated now; served on the DCC in a later milestone).
        if request.form.get("source") == "hf":
            hf_result = validate_hf_candidate(request.form.get("hf_repo", "").strip())
            return render_template("eval_run_new.html",
                                   hf_result=hf_result, **get_launch_options())

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

        from auth.session import require_private_access
        from frontend.eval_launch import (
            get_launch_options,
            start_run,
            validate_custom_questions,
            validate_hf_candidate,
            validate_launch,
            write_custom_suite,
        )

        user, auth_err = require_private_access()
        if auth_err:
            return auth_err, 403

        # Candidate source mirrors the standard start form: a gateway model runs
        # now; a Hugging Face model is validated now and served on the DCC in a
        # later milestone. The HF branch validates the model only (no run yet),
        # identical to /eval-run/start.
        if request.form.get("source") == "hf":
            hf_result = validate_hf_candidate(request.form.get("hf_repo", "").strip())
            return render_template("eval_run_new.html",
                                   hf_result=hf_result, **get_launch_options())

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

    @app.route("/eval-run/<slug>/delete", methods=["GET", "POST"])
    def eval_run_delete(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.eval_run_data import delete_eval_run
        from frontend.result_delete import eval_delete_context

        if request.method == "GET":
            ctx = eval_delete_context(slug)
            if ctx is None:
                return redirect(url_for("eval_run"))
            if ctx.get("error"):
                return ctx["error"], 400
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            return "confirmation required", 400
        error = delete_eval_run(slug)
        if error:
            return error, 400
        return redirect(url_for("eval_run"))

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

        from frontend.benchmark_launch import (
            HF_INFERENCE_BASE_URL,
            start_run,
            validate_launch,
        )

        benchmark_key = request.form.get("benchmark", "")
        model_source = request.form.get("model_source", "gateway")
        sample_raw = request.form.get("sample", "").strip()
        seed_raw = request.form.get("seed", "").strip()
        try:
            sample = int(sample_raw) if sample_raw else None
            seed = int(seed_raw) if seed_raw else None
        except ValueError:
            return "sample and seed must be integers", 400
        if model_source == "custom":
            model = request.form.get("custom_model", "").strip()
            base_url = request.form.get("base_url", "").strip()
            api_key = request.form.get("api_key", "").strip() or None
        elif model_source == "hosted":
            model = request.form.get("hosted_model", "").strip()
            base_url = HF_INFERENCE_BASE_URL
            api_key = request.form.get("hf_token", "").strip() or None
            if not api_key:
                return "enter your Hugging Face token", 400
        else:
            model = request.form.get("model", "")
            base_url = None
            api_key = None
        error = validate_launch(
            benchmark_key,
            model,
            base_url=base_url,
            sample=sample,
            seed=seed,
        )
        if error:
            return error, 400
        slug, _already = start_run(
            benchmark_key,
            model,
            base_url=base_url,
            api_key=api_key,
            sample=sample,
            seed=seed,
        )
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

    @app.route("/benchmarks/<slug>/delete", methods=["GET", "POST"])
    def benchmark_delete(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.benchmark_data import delete_benchmark
        from frontend.result_delete import benchmark_delete_context

        if request.method == "GET":
            ctx = benchmark_delete_context(slug)
            if ctx is None:
                return redirect(url_for("benchmarks"))
            if ctx.get("error"):
                return ctx["error"], 400
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            return "confirmation required", 400
        error = delete_benchmark(slug)
        if error:
            return error, 400
        return redirect(url_for("benchmarks"))

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
        redteam_profile = request.form.get("redteam_profile", "base")
        # Positive suite checkboxes from the new form UI
        run_policy = bool(request.form.get("run_policy"))
        run_redteam = bool(request.form.get("run_redteam"))
        run_garak = bool(request.form.get("run_garak"))
        # Derive skip flags from what the user selected
        skip_policy = not run_policy
        skip_redteam = not run_redteam
        skip_garak = not run_garak
        skip_promptfoo = skip_policy and skip_redteam
        garak_probes = request.form.get("garak_probes", "").strip()
        error = validate_launch(
            model,
            redteam_profile=redteam_profile,
            skip_policy=skip_policy,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes,
        )
        if error:
            return error, 400
        run_key, _already = start_run(
            model,
            redteam_profile=redteam_profile,
            skip_policy=skip_policy,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes or None,
        )
        slug, profile = run_key.split("/", 1)
        return redirect(url_for("safety_detail", slug=slug, profile=profile, status="running"))

    @app.route("/safety/<slug>/status")
    def safety_run_status_legacy(slug: str):
        from flask import redirect, url_for

        return redirect(url_for("safety_run_status", slug=slug, profile="base"))

    @app.route("/safety/<slug>")
    def safety_detail_legacy(slug: str):
        from flask import redirect, url_for

        return redirect(url_for("safety_detail", slug=slug, profile="base"))

    @app.route("/safety/<slug>/<profile>/status")
    def safety_run_status(slug: str, profile: str):
        from flask import jsonify

        from frontend.safety_launch import get_status

        return jsonify(get_status(slug, profile))

    @app.route("/safety/<slug>/<profile>")
    def safety_detail(slug: str, profile: str):
        from flask import request

        from frontend.safety_data import get_safety_detail
        from frontend.safety_launch import get_status

        detail = get_safety_detail(slug, profile)
        if detail is None or request.args.get("status") == "running":
            status = get_status(slug, profile)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "safety_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                    profile=profile,
                )

        if detail is None:
            return render_template(
                "safety_detail.html",
                missing=True,
                slug=slug,
                profile=profile,
            )
        return render_template("safety_detail.html", missing=False, **detail)

    @app.route("/safety/<slug>/<profile>/delete", methods=["GET", "POST"])
    def safety_delete(slug: str, profile: str):
        from flask import redirect, render_template, request, url_for

        from frontend.result_delete import safety_delete_context
        from frontend.safety_data import delete_safety

        if request.method == "GET":
            ctx = safety_delete_context(slug, profile)
            if ctx is None:
                return redirect(url_for("safety"))
            if ctx.get("error"):
                return ctx["error"], 400
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            return "confirmation required", 400
        error = delete_safety(slug, profile)
        if error:
            return error, 400
        return redirect(url_for("safety"))

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
