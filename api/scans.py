"""Scan read/write endpoints — thin wrappers over scan_data and scan_launch."""

from __future__ import annotations

from flask import Blueprint, url_for

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
from frontend import scan_data
from frontend import scan_launch
from frontend.output_dirs import OutputDirError
from frontend.path_safety import is_safe_slug

bp = Blueprint("scans_api", __name__)


@bp.get("/scans")
@json_errors
def list_scans():
    scans = scan_data.get_scans_data()["scans"]
    paging, error = parse_paging()
    if error is not None:
        return error
    limit, offset = paging
    page = scans[offset : offset + limit]
    return ok(page, meta=page_rows(scans, limit, offset))


@bp.get("/scans/<slug>")
@json_errors
def get_scan(slug: str):
    if not is_safe_slug(slug):
        return err("invalid scan id", 400)
    detail = scan_data.get_scan_detail(slug)
    if detail is None:
        return err("scan not found", 404)
    return ok(detail)


@bp.get("/scans/<slug>/status")
@json_errors
def scan_status(slug: str):
    if not is_safe_slug(slug):
        return err("invalid scan id", 400)
    return ok(scan_launch.get_status(slug))


@bp.post("/scans")
@json_errors
def start_scan():
    body = parse_json_body()
    hf_repo, field_err = require_str(body, "hf_repo")
    if field_err is not None:
        return field_err

    skip_modelscan = optional_bool(body, "skip_modelscan")
    skip_fickling = optional_bool(body, "skip_fickling")
    skip_modelaudit = optional_bool(body, "skip_modelaudit")
    skip_deps = optional_bool(body, "skip_deps")
    skip_secrets = optional_bool(body, "skip_secrets")

    launch_err = scan_launch.validate_launch(
        hf_repo,
        skip_modelscan=skip_modelscan,
        skip_fickling=skip_fickling,
        skip_modelaudit=skip_modelaudit,
        skip_deps=skip_deps,
        skip_secrets=skip_secrets,
    )
    if launch_err is not None:
        return validation_or_launch_error(launch_err)

    try:
        slug, already, _visibility = scan_launch.start_run(
            hf_repo,
            skip_modelscan=skip_modelscan,
            skip_fickling=skip_fickling,
            skip_modelaudit=skip_modelaudit,
            skip_deps=skip_deps,
            skip_secrets=skip_secrets,
        )
    except OutputDirError as exc:
        return launch_error_response(exc)
    return accepted(
        slug,
        url_for("scans_api.scan_status", slug=slug),
        already_running=already,
    )
