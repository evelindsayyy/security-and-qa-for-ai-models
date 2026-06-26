"""Safety read/write endpoints — thin wrappers over safety_data and safety_launch."""

from __future__ import annotations

from flask import Blueprint, request, url_for

from api.launch_helpers import (
    accepted,
    launch_error_response,
    optional_bool,
    parse_json_body,
    require_str,
    validation_or_launch_error,
)
from api.paging import page_rows, parse_paging
from api.responses import err, json_errors, ok
from frontend import safety_data
from frontend import safety_launch
from frontend.output_dirs import OutputDirError
from frontend.path_safety import is_safe_slug

bp = Blueprint("safety_api", __name__)


@bp.get("/safety")
@json_errors
def list_safety():
    models = safety_data.get_safety_data()["models"]
    profile = request.args.get("profile")
    if profile:
        models = [m for m in models if m.get("profile") == profile]

    paging, error = parse_paging()
    if error is not None:
        return error
    limit, offset = paging
    page = models[offset : offset + limit]
    return ok(page, meta=page_rows(models, limit, offset))


@bp.get("/safety/<slug>/<profile>")
@json_errors
def get_safety(slug: str, profile: str):
    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return err("invalid safety id", 400)
    detail = safety_data.get_safety_detail(slug, profile)
    if detail is None:
        return err("safety result not found", 404)
    return ok(detail)


@bp.get("/safety/<slug>/<profile>/status")
@json_errors
def safety_status(slug: str, profile: str):
    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return err("invalid safety id", 400)
    return ok(safety_launch.get_status(slug, profile))


@bp.post("/safety")
@json_errors
def start_safety():
    body = parse_json_body()
    model, field_err = require_str(body, "model")
    if field_err is not None:
        return field_err

    redteam_profile = body.get("redteam_profile", "base")
    if not isinstance(redteam_profile, str) or not redteam_profile.strip():
        return err("redteam_profile must be a non-empty string", 400)
    redteam_profile = redteam_profile.strip()

    run_policy = optional_bool(body, "run_policy", default=True)
    run_redteam = optional_bool(body, "run_redteam", default=True)
    run_garak = optional_bool(body, "run_garak", default=True)
    skip_policy = not run_policy
    skip_redteam = not run_redteam
    skip_garak = not run_garak
    skip_promptfoo = skip_policy and skip_redteam

    garak_probes = body.get("garak_probes")
    if garak_probes is not None and not isinstance(garak_probes, str):
        return err("garak_probes must be a string", 400)
    garak_probes = garak_probes.strip() if isinstance(garak_probes, str) and garak_probes.strip() else None

    launch_err = safety_launch.validate_launch(
        model,
        redteam_profile=redteam_profile,
        skip_policy=skip_policy,
        skip_redteam=skip_redteam,
        skip_garak=skip_garak,
        skip_promptfoo=skip_promptfoo,
        garak_probes=garak_probes,
    )
    if launch_err is not None:
        return validation_or_launch_error(launch_err)

    try:
        run_key, already = safety_launch.start_run(
            model,
            redteam_profile=redteam_profile,
            skip_policy=skip_policy,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes,
        )
    except OutputDirError as exc:
        return launch_error_response(exc)
    slug, profile = run_key.split("/", 1)
    return accepted(
        run_key,
        url_for("safety_api.safety_status", slug=slug, profile=profile),
        already_running=already,
    )
