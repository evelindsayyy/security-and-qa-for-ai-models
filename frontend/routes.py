"""
Flask routes for the AI Model Advisor frontend.

List and detail pages read pillar results via ``*_data.py`` modules.
Browser-launched runs use subprocess + polling.

Every pillar exposes two families of detail/status/delete routes:
public (``/scans/<slug>``, unchanged) and private (``/scans/<slug>/private``,
scoped to the signed-in user). ``_private_scope()`` resolves the latter from
the session — never from the ambient public/private view-mode toggle — so a
bookmarked private link keeps working even if the toggle is currently public.
"""

from __future__ import annotations

from flask import render_template

from auth.decorators import require_login
from auth.session import current_user_id
from gateway.catalog import get_gateway_catalog


def _private_scope() -> tuple[str, str]:
    """(visibility, owner_user_id) for the current user's ``/private`` routes.

    Every route that calls this is behind ``@require_login()``, so a user id
    is always present here.
    """
    return "private", current_user_id()


def _attach_pillar_summary(detail: dict, *, pillar: str) -> dict:
    from frontend.pillar_summary import attach_pillar_summary

    attach_pillar_summary(detail, pillar=pillar)
    return detail


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
    benchmark_latest = None

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
        from frontend.benchmark_data import get_benchmark_latest_for_hub, get_benchmarks_data

        bench = get_benchmarks_data()
        benchmark_has = bench["has_runs"]
        benchmark_count = len(bench["runs"])
        benchmark_latest = get_benchmark_latest_for_hub(bench.get("all_runs") or bench.get("runs"))
    except Exception:
        pass

    # Featured per-model report card (the AI Model Advisor label). Best-effort:
    # the home page never breaks if a pillar's data is missing.
    model_card = None
    try:
        from frontend.eval_run_data import featured_model_slug, get_model_card

        fslug = featured_model_slug()
        if fslug:
            model_card = get_model_card(fslug)
    except Exception:
        model_card = None

    gw = get_gateway_catalog()
    return {
        "model_card": model_card,
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
        "benchmark_latest": benchmark_latest,
    }


def register_routes(app):
    @app.route("/")
    def index():
        from frontend.overview import get_overview_data

        return render_template("index.html", **get_overview_data())

    @app.route("/jobs")
    def inflight_jobs():
        from frontend.launch_registry import list_inflight_jobs

        return render_template("jobs.html", jobs=list_inflight_jobs())

    @app.route("/scans")
    def scans():
        from frontend.scan_data import get_scan_guide_data, get_scans_data

        data = get_scans_data()
        data.update(get_scan_guide_data(data.get("scans")))
        return render_template("scans.html", **data)

    @app.route("/scans/new")
    @require_login()
    def scan_run_new():
        from flask import request

        from frontend.read_context import read_context
        from frontend.scan_data import get_scan_rerun_params
        from frontend.scan_launch import get_launch_options

        opts = get_launch_options()
        from_slug = request.args.get("from", "").strip()
        if from_slug:
            visibility, owner_user_id = read_context()
            opts["rerun"] = get_scan_rerun_params(
                from_slug, visibility=visibility, owner_user_id=owner_user_id
            )
        return render_template("scan_run_new.html", **opts)

    @app.route("/scans/start", methods=["POST"])
    @require_login()
    def scan_run_start():
        from flask import redirect, request, url_for

        from frontend import docker_launch
        from frontend.output_dirs import OutputDirError
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
        try:
            slug, already, visibility = start_run(
                hf_repo,
                skip_modelscan=not request.form.get("run_modelscan"),
                skip_fickling=not request.form.get("run_fickling"),
                skip_modelaudit=not request.form.get("run_modelaudit"),
                skip_deps=not request.form.get("run_deps"),
                skip_secrets=not request.form.get("run_secrets"),
            )
        except OutputDirError as exc:
            return str(exc), 503
        except docker_launch.DockerUnavailableError as exc:
            return str(exc), 503
        status = "reused" if already else "running"
        endpoint = "scan_detail_private" if visibility == "private" else "scan_detail"
        return redirect(url_for(endpoint, slug=slug, status=status))

    @app.route("/scans/<slug>/status")
    def scan_run_status(slug: str):
        from flask import jsonify

        from frontend.scan_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/scans/<slug>/private/status")
    @require_login()
    def scan_run_status_private(slug: str):
        from flask import jsonify

        from frontend.scan_launch import get_status

        visibility, owner_user_id = _private_scope()
        return jsonify(get_status(slug, visibility=visibility, owner_user_id=owner_user_id))

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
        return render_template("scan_detail.html", missing=False, **_attach_pillar_summary(detail, pillar="scan"))

    @app.route("/scans/<slug>/private")
    @require_login()
    def scan_detail_private(slug: str):
        from flask import request

        from frontend.scan_data import get_scan_detail

        visibility, owner_user_id = _private_scope()
        detail = get_scan_detail(slug, visibility=visibility, owner_user_id=owner_user_id)
        if detail is None or request.args.get("status") == "running":
            from frontend.scan_launch import get_status

            status = get_status(slug, visibility=visibility, owner_user_id=owner_user_id)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "scan_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                    is_private=True,
                )

        if detail is None:
            return render_template(
                "scan_detail.html",
                missing=True,
                slug=slug,
                is_private=True,
            )
        return render_template("scan_detail.html", missing=False, is_private=True, **_attach_pillar_summary(detail, pillar="scan"))

    @app.route("/scans/<slug>/delete", methods=["GET", "POST"])
    @require_login()
    def scan_delete(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.result_delete import scan_delete_context
        from frontend.scan_data import delete_scan

        if request.method == "GET":
            ctx = scan_delete_context(slug)
            if ctx is None:
                return redirect(url_for("scans"))
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = scan_delete_context(slug, error_message="Confirmation required.")
            if ctx is None:
                return redirect(url_for("scans"))
            return render_template("delete_confirm.html", **ctx)
        error = delete_scan(slug)
        if error:
            ctx = scan_delete_context(slug, error_message=error)
            if ctx is None:
                return redirect(url_for("scans"))
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("scans"))

    @app.route("/scans/<slug>/private/delete", methods=["GET", "POST"])
    @require_login()
    def scan_delete_private(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.result_delete import scan_delete_context
        from frontend.scan_data import delete_scan

        visibility, owner_user_id = _private_scope()
        if request.method == "GET":
            ctx = scan_delete_context(slug, visibility=visibility, owner_user_id=owner_user_id)
            if ctx is None:
                return redirect(url_for("scans"))
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = scan_delete_context(
                slug, visibility=visibility, owner_user_id=owner_user_id,
                error_message="Confirmation required.",
            )
            if ctx is None:
                return redirect(url_for("scans"))
            return render_template("delete_confirm.html", **ctx)
        error = delete_scan(slug, visibility=visibility, owner_user_id=owner_user_id)
        if error:
            ctx = scan_delete_context(
                slug, visibility=visibility, owner_user_id=owner_user_id, error_message=error,
            )
            if ctx is None:
                return redirect(url_for("scans"))
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("scans"))

    @app.route("/eval-run")
    def eval_run():
        from frontend.eval_run_data import get_eval_guide_data, get_runs_data

        data = get_runs_data()
        data.update(get_eval_guide_data())
        return render_template("eval_run.html", **data)

    @app.route("/eval-run/new")
    @require_login()
    def eval_run_new():
        from flask import request

        from frontend.eval_launch import get_launch_options
        from frontend.eval_run_data import get_eval_rerun_params
        from frontend.read_context import read_context

        opts = get_launch_options()
        from_slug = request.args.get("from", "").strip()
        if from_slug:
            visibility, owner_user_id = read_context()
            opts["rerun"] = get_eval_rerun_params(
                from_slug, visibility=visibility, owner_user_id=owner_user_id
            )
        return render_template("eval_run_new.html", **opts)

    @app.route("/eval-run/start", methods=["POST"])
    @require_login()
    def eval_run_start():
        from flask import redirect, request, url_for

        from frontend.eval_launch import (
            get_launch_options,
            start_dcc_run,
            start_run,
            validate_dcc_params,
            validate_hf_candidate,
            validate_hf_scan_gate,
            validate_launch,
        )
        from frontend import docker_launch
        from frontend.output_dirs import OutputDirError

        # Candidate source: a gateway model (runs on the gateway) or a Hugging
        # Face model (served + evaluated + torn down on the DCC via the
        # orchestrator). The HF branch validates servability first — an
        # unservable model never starts a GPU job — then the run params.
        if request.form.get("source") == "hf":
            hf_repo = request.form.get("hf_repo", "").strip()

            # Servability first: an unservable model never starts a GPU job — show
            # the reason inline (before parsing the other params, so a bad model
            # reports its reason rather than a max_tokens error).
            hf_result = validate_hf_candidate(hf_repo)
            if not hf_result["ok"]:
                return render_template("eval_run_new.html",
                                       hf_result=hf_result, **get_launch_options())
            scan_gate = validate_hf_scan_gate(hf_repo)
            if not scan_gate["ok"]:
                hf_result = {**hf_result, "ok": False, "error": scan_gate["error"],
                             "scan_gate": scan_gate}
                return render_template("eval_run_new.html",
                                       hf_result=hf_result, **get_launch_options())

            judge = request.form.get("judge", "")
            suite_key = request.form.get("suite", "")
            try:
                max_tokens = int(request.form.get("max_tokens", ""))
            except ValueError:
                return "max_tokens must be an integer", 400
            error = validate_dcc_params(hf_repo, judge, suite_key, max_tokens)
            if error is not None:
                return error, 400
            try:
                slug, _already = start_dcc_run(hf_repo, judge, suite_key, max_tokens)
            except docker_launch.DockerUnavailableError as exc:
                return str(exc), 503
            return redirect(url_for("eval_run_detail", slug=slug, status="running"))

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

        # Cross-pillar gate: a gateway model must clear safety red-teaming
        # before it can be evaluated (scan is N/A for gateway endpoints).
        from frontend import pipeline

        gate_error = pipeline.require_ready_for_downstream(candidate, "gateway")
        if gate_error is not None:
            return gate_error, 400

        try:
            slug, _already, visibility = start_run(candidate, judge, suite_key, max_tokens)
        except OutputDirError as exc:
            return str(exc), 503
        except docker_launch.DockerUnavailableError as exc:
            return str(exc), 503
        endpoint = "eval_run_detail_private" if visibility == "private" else "eval_run_detail"
        return redirect(url_for(endpoint, slug=slug, status="running"))

    @app.route("/eval-run/start-custom", methods=["POST"])
    def eval_run_start_custom():
        from flask import redirect, request, url_for

        from auth.session import require_private_access
        from frontend.eval_launch import (
            get_launch_options,
            start_dcc_run,
            start_run,
            validate_dcc_params,
            validate_custom_questions,
            validate_hf_candidate,
            validate_hf_scan_gate,
            validate_launch,
            write_custom_suite,
        )
        from frontend import docker_launch

        user, auth_err = require_private_access()
        if auth_err:
            return auth_err, 403

        # Candidate source mirrors the standard start form: a gateway model runs
        # locally; a Hugging Face model must pass servability + scanner clearance
        # and then launches through the DCC orchestrator.
        if request.form.get("source") == "hf":
            hf_repo = request.form.get("hf_repo", "").strip()
            hf_result = validate_hf_candidate(hf_repo)
            if not hf_result["ok"]:
                return render_template("eval_run_new.html",
                                       hf_result=hf_result, **get_launch_options())
            scan_gate = validate_hf_scan_gate(hf_repo)
            if not scan_gate["ok"]:
                hf_result = {**hf_result, "ok": False, "error": scan_gate["error"],
                             "scan_gate": scan_gate}
                return render_template("eval_run_new.html",
                                       hf_result=hf_result, **get_launch_options())

            judge = request.form.get("judge", "")
            try:
                max_tokens = int(request.form.get("max_tokens", ""))
            except ValueError:
                return "max_tokens must be an integer", 400

            questions, q_error = validate_custom_questions(request.form.get("questions", ""))
            if q_error is not None:
                return f"custom questions: {q_error}", 400

            suite_key = write_custom_suite(questions)
            error = validate_dcc_params(hf_repo, judge, suite_key, max_tokens)
            if error is not None:
                return error, 400

            try:
                slug, _already = start_dcc_run(hf_repo, judge, suite_key, max_tokens)
            except docker_launch.DockerUnavailableError as exc:
                return str(exc), 503
            return redirect(url_for("eval_run_detail", slug=slug, status="running"))

        candidate = request.form.get("candidate", "")
        judge = request.form.get("judge", "")
        try:
            max_tokens = int(request.form.get("max_tokens", ""))
        except ValueError:
            return "max_tokens must be an integer", 400

        # Allowlist the candidate BEFORE the gate so no unvalidated value reaches
        # the safety-artifact path lookup. The standard path allowlists first via
        # validate_launch; here validate_launch runs later (it needs the suite
        # key), so the candidate check is hoisted up front. The message does not
        # reflect the raw candidate, so no HTML-escaping is needed.
        from frontend.eval_launch import candidate_models

        if candidate not in candidate_models():
            return "candidate model not in allowlist", 400

        # Cross-pillar gate before we write any custom-suite file: a gateway
        # model must clear safety red-teaming first (scan is N/A for gateway).
        from frontend import pipeline

        gate_error = pipeline.require_ready_for_downstream(candidate, "gateway")
        if gate_error is not None:
            return gate_error, 400

        # Validate the user's pasted questions as data before anything touches
        # the filesystem or a subprocess (the custom-content security boundary).
        questions, q_error = validate_custom_questions(request.form.get("questions", ""))
        if q_error is not None:
            return f"custom questions: {q_error}", 400

        suite_key = write_custom_suite(questions)
        error = validate_launch(candidate, judge, suite_key, max_tokens)
        if error is not None:
            return error, 400

        try:
            slug, _already, visibility = start_run(candidate, judge, suite_key, max_tokens)
        except docker_launch.DockerUnavailableError as exc:
            return str(exc), 503
        endpoint = "eval_run_detail_private" if visibility == "private" else "eval_run_detail"
        return redirect(url_for(endpoint, slug=slug, status="running"))

    @app.route("/eval-run/<slug>/status")
    def eval_run_status(slug: str):
        from flask import jsonify

        from frontend.eval_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/eval-run/<slug>/private/status")
    @require_login()
    def eval_run_status_private(slug: str):
        from flask import jsonify

        from frontend.eval_launch import get_status

        visibility, owner_user_id = _private_scope()
        return jsonify(get_status(slug, visibility=visibility, owner_user_id=owner_user_id))

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
            if status["status"] not in ("not_found", "done"):
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
        return render_template("eval_run_detail.html", missing=False, **_attach_pillar_summary(detail, pillar="eval"))

    @app.route("/eval-run/<slug>/private")
    @require_login()
    def eval_run_detail_private(slug: str):
        from flask import request

        from frontend.eval_run_data import get_run_detail

        visibility, owner_user_id = _private_scope()
        detail = get_run_detail(slug, visibility=visibility, owner_user_id=owner_user_id)

        if detail is None or request.args.get("status") == "running":
            from frontend.eval_launch import get_status

            status = get_status(slug, visibility=visibility, owner_user_id=owner_user_id)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "eval_run_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                    is_private=True,
                )

        if detail is None:
            return render_template(
                "eval_run_detail.html",
                missing=True,
                slug=slug,
                is_private=True,
            )
        return render_template("eval_run_detail.html", missing=False, is_private=True, **_attach_pillar_summary(detail, pillar="eval"))

    @app.route("/eval-run/<slug>/delete", methods=["GET", "POST"])
    @require_login()
    def eval_run_delete(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.eval_run_data import delete_eval_combo_from_slug
        from frontend.result_delete import eval_delete_context

        if request.method == "GET":
            ctx = eval_delete_context(slug)
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = eval_delete_context(slug, error_message="Confirmation required.")
            return render_template("delete_confirm.html", **ctx)
        error = delete_eval_combo_from_slug(slug)
        if error:
            ctx = eval_delete_context(slug, error_message=error)
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("eval_run"))

    @app.route("/eval-run/<slug>/private/delete", methods=["GET", "POST"])
    @require_login()
    def eval_run_delete_private(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.eval_run_data import delete_eval_combo_from_slug
        from frontend.result_delete import eval_delete_context

        visibility, owner_user_id = _private_scope()
        if request.method == "GET":
            ctx = eval_delete_context(slug, visibility=visibility, owner_user_id=owner_user_id)
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = eval_delete_context(
                slug, visibility=visibility, owner_user_id=owner_user_id,
                error_message="Confirmation required.",
            )
            return render_template("delete_confirm.html", **ctx)
        error = delete_eval_combo_from_slug(
            slug, visibility=visibility, owner_user_id=owner_user_id
        )
        if error:
            ctx = eval_delete_context(
                slug, visibility=visibility, owner_user_id=owner_user_id, error_message=error,
            )
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("eval_run"))

    @app.route("/benchmarks")
    def benchmarks():
        from frontend.benchmark_data import get_benchmark_guide_data, get_benchmarks_data

        data = get_benchmarks_data()
        data.update(get_benchmark_guide_data())
        return render_template("benchmarks.html", **data)

    @app.route("/benchmarks/new")
    @require_login()
    def benchmark_run_new():
        from flask import request

        from frontend.benchmark_data import get_benchmark_rerun_params
        from frontend.benchmark_launch import get_launch_options

        opts = get_launch_options()
        from_slug = request.args.get("from", "").strip()
        if from_slug:
            from frontend.read_context import read_context

            visibility, owner_user_id = read_context()
            opts["rerun"] = get_benchmark_rerun_params(
                from_slug, visibility=visibility, owner_user_id=owner_user_id
            )
        return render_template("benchmark_run_new.html", **opts)

    @app.route("/benchmarks/start", methods=["POST"])
    @require_login()
    def benchmark_run_start():
        from flask import redirect, request, url_for

        from frontend.benchmark_launch import (
            HF_INFERENCE_BASE_URL,
            start_run,
            validate_launch,
        )
        from frontend.output_dirs import OutputDirError

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

        # Same cross-pillar gate as eval: gateway → safety; HF hosted → scan.
        from frontend import pipeline

        if model_source == "hosted":
            gate_error = pipeline.require_ready_for_downstream(model, "hf")
            if gate_error is not None:
                return gate_error, 400
        elif model_source == "gateway":
            gate_error = pipeline.require_ready_for_downstream(model, "gateway")
            if gate_error is not None:
                return gate_error, 400

        error = validate_launch(
            benchmark_key,
            model,
            base_url=base_url,
            sample=sample,
            seed=seed,
        )
        if error:
            return error, 400
        try:
            slug, already, visibility = start_run(
                benchmark_key,
                model,
                base_url=base_url,
                api_key=api_key,
                sample=sample,
                seed=seed,
            )
        except OutputDirError as exc:
            return str(exc), 503
        endpoint = "benchmark_detail_private" if visibility == "private" else "benchmark_detail"
        status = "running"
        return redirect(url_for(endpoint, slug=slug, status=status))

    @app.route("/benchmarks/<slug>/status")
    def benchmark_run_status(slug: str):
        from flask import jsonify

        from frontend.benchmark_launch import get_status

        return jsonify(get_status(slug))

    @app.route("/benchmarks/<slug>/cancel", methods=["POST"])
    @require_login()
    def benchmark_cancel(slug: str):
        from flask import jsonify, request

        from frontend.benchmark_launch import cancel_run
        from frontend.read_context import read_context

        visibility, owner_user_id = read_context()
        error = cancel_run(slug, visibility=visibility, owner_user_id=owner_user_id)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": True, "status": "cancelled"})
        from flask import redirect, url_for

        return redirect(url_for("benchmark_detail", slug=slug, status="cancelled"))

    @app.route("/benchmarks/<slug>/private/status")
    @require_login()
    def benchmark_run_status_private(slug: str):
        from flask import jsonify

        from frontend.benchmark_launch import get_status

        visibility, owner_user_id = _private_scope()
        return jsonify(get_status(slug, visibility=visibility, owner_user_id=owner_user_id))

    @app.route("/benchmarks/<slug>/private/cancel", methods=["POST"])
    @require_login()
    def benchmark_cancel_private(slug: str):
        from flask import jsonify, request

        from frontend.benchmark_launch import cancel_run

        visibility, owner_user_id = _private_scope()
        error = cancel_run(slug, visibility=visibility, owner_user_id=owner_user_id)
        if error:
            return jsonify({"ok": False, "error": error}), 400
        if request.accept_mimetypes.best == "application/json":
            return jsonify({"ok": True, "status": "cancelled"})
        from flask import redirect, url_for

        return redirect(url_for("benchmark_detail_private", slug=slug, status="cancelled"))

    @app.route("/benchmarks/<slug>")
    def benchmark_detail(slug: str):
        from flask import request

        from frontend.benchmark_data import get_benchmark_detail

        detail = get_benchmark_detail(slug)
        if detail is None or request.args.get("status") == "running":
            from frontend.benchmark_launch import get_status

            status = get_status(slug)
            if status["status"] in ("running", "failed", "cancelled"):
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
        return render_template("benchmark_detail.html", missing=False, **_attach_pillar_summary(detail, pillar="benchmark"))

    @app.route("/benchmarks/<slug>/private")
    @require_login()
    def benchmark_detail_private(slug: str):
        from flask import request

        from frontend.benchmark_data import get_benchmark_detail

        visibility, owner_user_id = _private_scope()
        detail = get_benchmark_detail(slug, visibility=visibility, owner_user_id=owner_user_id)
        if detail is None or request.args.get("status") == "running":
            from frontend.benchmark_launch import get_status

            status = get_status(slug, visibility=visibility, owner_user_id=owner_user_id)
            if status["status"] in ("running", "failed", "cancelled"):
                return render_template(
                    "benchmark_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                    is_private=True,
                )

        if detail is None:
            return render_template(
                "benchmark_detail.html",
                missing=True,
                slug=slug,
                is_private=True,
            )
        return render_template("benchmark_detail.html", missing=False, is_private=True, **_attach_pillar_summary(detail, pillar="benchmark"))

    @app.route("/benchmarks/<slug>/items")
    def benchmark_detail_items(slug: str):
        from flask import jsonify, render_template, request

        from frontend.benchmark_data import get_benchmark_detail_items

        offset = max(0, request.args.get("offset", 0, type=int))
        page = get_benchmark_detail_items(slug, offset)
        if page is None:
            return jsonify({"error": "not found"}), 404
        html = render_template(
            f"benchmark_detail/_{page['kind']}_items.html",
            show_heading=False,
            **page,
        )
        return jsonify({
            "html": html,
            "offset": page["items_loaded"],
            "has_more": page["items_has_more"],
            "total": page["raw_row_count"],
        })

    @app.route("/benchmarks/<slug>/private/items")
    @require_login()
    def benchmark_detail_items_private(slug: str):
        from flask import jsonify, render_template, request

        from frontend.benchmark_data import get_benchmark_detail_items

        visibility, owner_user_id = _private_scope()
        offset = max(0, request.args.get("offset", 0, type=int))
        page = get_benchmark_detail_items(
            slug, offset, visibility=visibility, owner_user_id=owner_user_id
        )
        if page is None:
            return jsonify({"error": "not found"}), 404
        html = render_template(
            f"benchmark_detail/_{page['kind']}_items.html",
            show_heading=False,
            **page,
        )
        return jsonify({
            "html": html,
            "offset": page["items_loaded"],
            "has_more": page["items_has_more"],
            "total": page["raw_row_count"],
        })

    @app.route("/benchmarks/<slug>/delete", methods=["GET", "POST"])
    @require_login()
    def benchmark_delete(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.benchmark_data import delete_benchmark
        from frontend.result_delete import benchmark_delete_context

        if request.method == "GET":
            ctx = benchmark_delete_context(slug)
            if ctx is None:
                return redirect(url_for("benchmarks"))
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = benchmark_delete_context(slug, error_message="Confirmation required.")
            if ctx is None:
                return redirect(url_for("benchmarks"))
            return render_template("delete_confirm.html", **ctx)
        error = delete_benchmark(slug)
        if error:
            ctx = benchmark_delete_context(slug, error_message=error)
            if ctx is None:
                return redirect(url_for("benchmarks"))
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("benchmarks"))

    @app.route("/benchmarks/<slug>/private/delete", methods=["GET", "POST"])
    @require_login()
    def benchmark_delete_private(slug: str):
        from flask import redirect, render_template, request, url_for

        from frontend.benchmark_data import delete_benchmark
        from frontend.result_delete import benchmark_delete_context

        visibility, owner_user_id = _private_scope()
        if request.method == "GET":
            ctx = benchmark_delete_context(slug, visibility=visibility, owner_user_id=owner_user_id)
            if ctx is None:
                return redirect(url_for("benchmarks"))
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = benchmark_delete_context(
                slug, visibility=visibility, owner_user_id=owner_user_id,
                error_message="Confirmation required.",
            )
            if ctx is None:
                return redirect(url_for("benchmarks"))
            return render_template("delete_confirm.html", **ctx)
        error = delete_benchmark(slug, visibility=visibility, owner_user_id=owner_user_id)
        if error:
            ctx = benchmark_delete_context(
                slug, visibility=visibility, owner_user_id=owner_user_id, error_message=error,
            )
            if ctx is None:
                return redirect(url_for("benchmarks"))
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("benchmarks"))

    @app.route("/safety")
    def safety():
        from frontend.safety_data import get_safety_data, get_safety_guide_data

        data = get_safety_data()
        data.update(get_safety_guide_data())
        return render_template("safety.html", **data)

    @app.route("/safety/new")
    @require_login()
    def safety_run_new():
        from flask import request

        from frontend.read_context import read_context
        from frontend.safety_data import get_safety_rerun_params
        from frontend.safety_launch import get_launch_options

        opts = get_launch_options()
        from_slug = request.args.get("from", "").strip()
        profile = request.args.get("profile", "base").strip() or "base"
        if from_slug:
            visibility, owner_user_id = read_context()
            opts["rerun"] = get_safety_rerun_params(
                from_slug, profile, visibility=visibility, owner_user_id=owner_user_id
            )
        return render_template("safety_run_new.html", **opts)

    @app.route("/safety/start", methods=["POST"])
    @require_login()
    def safety_run_start():
        from flask import redirect, request, url_for

        from frontend.safety_launch import start_run, validate_launch
        from frontend import docker_launch
        from frontend.output_dirs import OutputDirError

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
        try:
            run_key, _already, visibility = start_run(
                model,
                redteam_profile=redteam_profile,
                skip_policy=skip_policy,
                skip_redteam=skip_redteam,
                skip_garak=skip_garak,
                skip_promptfoo=skip_promptfoo,
                garak_probes=garak_probes or None,
            )
        except OutputDirError as exc:
            return str(exc), 503
        except docker_launch.DockerUnavailableError as exc:
            return str(exc), 503
        slug, profile = run_key.split("/", 1)
        endpoint = "safety_detail_private" if visibility == "private" else "safety_detail"
        return redirect(url_for(endpoint, slug=slug, profile=profile, status="running"))

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

    @app.route("/safety/<slug>/<profile>/private/status")
    @require_login()
    def safety_run_status_private(slug: str, profile: str):
        from flask import jsonify

        from frontend.safety_launch import get_status

        visibility, owner_user_id = _private_scope()
        return jsonify(
            get_status(slug, profile, visibility=visibility, owner_user_id=owner_user_id)
        )

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
        return render_template("safety_detail.html", missing=False, **_attach_pillar_summary(detail, pillar="safety"))

    @app.route("/safety/<slug>/<profile>/private")
    @require_login()
    def safety_detail_private(slug: str, profile: str):
        from flask import request

        from frontend.safety_data import get_safety_detail
        from frontend.safety_launch import get_status

        visibility, owner_user_id = _private_scope()
        detail = get_safety_detail(
            slug, profile, visibility=visibility, owner_user_id=owner_user_id
        )
        if detail is None or request.args.get("status") == "running":
            status = get_status(slug, profile, visibility=visibility, owner_user_id=owner_user_id)
            if status["status"] in ("running", "failed"):
                return render_template(
                    "safety_detail.html",
                    missing=False,
                    running=True,
                    run_status=status,
                    slug=slug,
                    profile=profile,
                    is_private=True,
                )

        if detail is None:
            return render_template(
                "safety_detail.html",
                missing=True,
                slug=slug,
                profile=profile,
                is_private=True,
            )
        return render_template("safety_detail.html", missing=False, is_private=True, **_attach_pillar_summary(detail, pillar="safety"))

    @app.route("/safety/<slug>/<profile>/delete", methods=["GET", "POST"])
    @require_login()
    def safety_delete(slug: str, profile: str):
        from flask import redirect, render_template, request, url_for

        from frontend.result_delete import safety_delete_context
        from frontend.safety_data import delete_safety

        if request.method == "GET":
            ctx = safety_delete_context(slug, profile)
            if ctx is None:
                return redirect(url_for("safety"))
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = safety_delete_context(slug, profile, error_message="Confirmation required.")
            if ctx is None:
                return redirect(url_for("safety"))
            return render_template("delete_confirm.html", **ctx)
        error = delete_safety(slug, profile)
        if error:
            ctx = safety_delete_context(slug, profile, error_message=error)
            if ctx is None:
                return redirect(url_for("safety"))
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("safety"))

    @app.route("/safety/<slug>/<profile>/private/delete", methods=["GET", "POST"])
    @require_login()
    def safety_delete_private(slug: str, profile: str):
        from flask import redirect, render_template, request, url_for

        from frontend.result_delete import safety_delete_context
        from frontend.safety_data import delete_safety

        visibility, owner_user_id = _private_scope()
        if request.method == "GET":
            ctx = safety_delete_context(
                slug, profile, visibility=visibility, owner_user_id=owner_user_id
            )
            if ctx is None:
                return redirect(url_for("safety"))
            return render_template("delete_confirm.html", **ctx)
        if request.form.get("confirm") != "1":
            ctx = safety_delete_context(
                slug, profile, visibility=visibility, owner_user_id=owner_user_id,
                error_message="Confirmation required.",
            )
            if ctx is None:
                return redirect(url_for("safety"))
            return render_template("delete_confirm.html", **ctx)
        error = delete_safety(slug, profile, visibility=visibility, owner_user_id=owner_user_id)
        if error:
            ctx = safety_delete_context(
                slug, profile, visibility=visibility, owner_user_id=owner_user_id,
                error_message=error,
            )
            if ctx is None:
                return redirect(url_for("safety"))
            return render_template("delete_confirm.html", **ctx)
        return redirect(url_for("safety"))

    @app.route("/models")
    def models_catalog():
        from frontend import model_rollup

        gw = get_gateway_catalog()
        rollup_by_gateway_id = model_rollup.rollups_for_gateway_ids(
            [m["id"] for m in gw["models"]]
        )
        gateway_by_category = []
        for section in gw["by_category"]:
            models = sorted(
                section["models"],
                key=lambda m: (
                    rollup_by_gateway_id[m["id"]].get("aggregate") is None,
                    -(rollup_by_gateway_id[m["id"]].get("aggregate") or 0),
                    m["id"].lower(),
                ),
            )
            gateway_by_category.append({**section, "models": models})
        return render_template(
            "catalog.html",
            gateway=gw["models"],
            gateway_by_category=gateway_by_category,
            gateway_count=gw["count"],
            gateway_source=gw["source"],
            gateway_fetched_at=gw["fetched_at"],
            gateway_error=gw["error"],
            gateway_deprecated=gw["deprecated"],
            rollup_by_gateway_id=rollup_by_gateway_id,
        )

    @app.route("/models/<slug>")
    def model_detail(slug: str):
        from frontend import model_rollup, model_summary
        from frontend.eval_run_data import get_model_detail
        from frontend.model_identity import gateway_is_hf_scannable, gateway_slug

        rollup = model_rollup.get_model_rollup(slug)
        gateway_profile = None
        gateway_id = None
        if rollup is None:
            gw = get_gateway_catalog()
            for m in gw["models"]:
                if gateway_slug(m["id"]) == slug:
                    gateway_id = m["id"]
                    gateway_profile = m.get("notes")
                    rollup = model_rollup.empty_gateway_rollup(m["id"])
                    break
            if rollup is None:
                return render_template("model_detail.html", missing=True, slug=slug)

        detail = get_model_detail(slug) or {
            "model": rollup["display_name"], "runs": [], "dim_columns": [],
            "n_runs": 0, "suites": [], "avg_overall": None, "best_overall": None, "total_cost_usd": 0,
        }
        recommendation = model_summary.get_recommendation_summary(rollup)
        can_hf_scan = gateway_is_hf_scannable(rollup["display_name"])
        from frontend.model_findings import get_model_findings
        from frontend import scan_data
        from frontend.scan_links import get_linked_scan

        pillar_findings = get_model_findings(rollup)
        linked_scan_slug = get_linked_scan(rollup["display_name"])
        available_scans = [
            {"slug": s["slug"], "model_id": s.get("model_id"), "tier": s.get("severity_tier")}
            for s in scan_data.get_scans_data().get("scans", [])
        ]
        return render_template(
            "model_detail.html",
            missing=False,
            rollup=rollup,
            recommendation=recommendation,
            pillar_findings=pillar_findings,
            gateway_profile=gateway_profile,
            gateway_id=gateway_id or rollup["display_name"],
            can_hf_scan=can_hf_scan,
            linked_scan_slug=linked_scan_slug,
            available_scans=available_scans,
            **detail,
        )

    @app.route("/compare")
    def compare_models():
        from flask import request

        from frontend import model_rollup, model_summary
        from frontend.model_identity import gateway_slug

        raw = request.args.get("models", "")
        slugs = [s for s in (p.strip() for p in raw.split(",")) if s]
        gw = get_gateway_catalog()
        id_by_slug = {gateway_slug(m["id"]): m["id"] for m in gw["models"]}
        rollups = []
        for slug in slugs:
            rollup = model_rollup.get_model_rollup(slug)
            if rollup is None and slug in id_by_slug:
                rollup = model_rollup.empty_gateway_rollup(id_by_slug[slug])
            if rollup is not None:
                rollups.append(rollup)
        recommendations = {
            r["slug"]: model_summary.get_recommendation_summary(r) for r in rollups
        }
        compare_summary = model_summary.get_compare_summary(rollups) if len(rollups) >= 2 else None
        unmatched = [s for s in slugs if s not in {r["slug"] for r in rollups}]
        benchmark_kinds = sorted({
            kind
            for r in rollups
            for kind in (r.get("benchmark") or {}).get("kinds", {})
        })
        chart_models = []
        for r in rollups:
            bench = {}
            for kind, info in (r.get("benchmark") or {}).get("kinds", {}).items():
                bench[kind] = {
                    "headline_value": info.get("headline_value"),
                    "headline_display": info.get("headline_display"),
                }
            chart_models.append(
                {
                    "slug": r["slug"],
                    "display_name": r.get("display_name", r["slug"]),
                    "scan": r.get("scan"),
                    "safety": r.get("safety"),
                    "eval": r.get("eval"),
                    "benchmark": bench,
                }
            )
        return render_template(
            "compare.html",
            rollups=rollups,
            recommendations=recommendations,
            compare_summary=compare_summary,
            requested_slugs=slugs,
            unmatched=unmatched,
            benchmark_kinds=benchmark_kinds,
            chart_models=chart_models,
        )

    @app.route("/models/<slug>/link-scan", methods=["POST"])
    @require_login()
    def model_link_scan(slug: str):
        from flask import flash, redirect, request, url_for

        from frontend import model_rollup
        from frontend.scan_links import set_link

        rollup = model_rollup.get_model_rollup(slug)
        gateway_id = (rollup or {}).get("display_name") or slug
        scan_slug = (request.form.get("scan_slug") or "").strip()
        err = set_link(gateway_model_id=gateway_id, scan_slug=scan_slug)
        if err:
            flash(err, "error")
        else:
            flash(f"Linked scan {scan_slug!r} to this model.", "success")
        return redirect(url_for("model_detail", slug=slug))

    @app.route("/models/<slug>/unlink-scan", methods=["POST"])
    @require_login()
    def model_unlink_scan(slug: str):
        from flask import redirect, url_for

        from frontend import model_rollup
        from frontend.scan_links import remove_link

        rollup = model_rollup.get_model_rollup(slug)
        gateway_id = (rollup or {}).get("display_name") or slug
        remove_link(gateway_model_id=gateway_id)
        return redirect(url_for("model_detail", slug=slug))

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
