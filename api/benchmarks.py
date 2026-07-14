"""Benchmark read/write endpoints — thin wrappers over benchmark_data and benchmark_launch."""

from __future__ import annotations

from flask import Blueprint, url_for

from api.launch_helpers import (
    accepted,
    parse_json_body,
    require_str,
    validation_error,
)
from api.paging import page_rows, parse_paging
from api.responses import err, json_errors, ok
from frontend import benchmark_data
from frontend import benchmark_launch
from frontend.path_safety import is_safe_slug

bp = Blueprint("benchmarks_api", __name__)


@bp.get("/benchmarks")
@json_errors
def list_benchmarks():
    runs = benchmark_data.get_benchmarks_data()["runs"]
    paging, error = parse_paging()
    if error is not None:
        return error
    limit, offset = paging
    page = runs[offset : offset + limit]
    return ok(page, meta=page_rows(runs, limit, offset))


@bp.get("/benchmarks/<slug>")
@json_errors
def get_benchmark(slug: str):
    if not is_safe_slug(slug):
        return err("invalid benchmark id", 400)
    detail = benchmark_data.get_benchmark_detail(slug)
    if detail is None:
        return err("benchmark not found", 404)
    return ok(detail)


@bp.get("/benchmarks/<slug>/status")
@json_errors
def benchmark_status(slug: str):
    if not is_safe_slug(slug):
        return err("invalid benchmark id", 400)
    return ok(benchmark_launch.get_status(slug))


@bp.post("/benchmarks")
@json_errors
def start_benchmark():
    body = parse_json_body()
    benchmark_key, bench_err = require_str(body, "benchmark")
    if bench_err is not None:
        return bench_err
    model, model_err = require_str(body, "model")
    if model_err is not None:
        return model_err

    launch_err = benchmark_launch.validate_launch(benchmark_key, model)
    if launch_err is not None:
        return validation_error(launch_err)

    from frontend import pipeline

    gate_err = pipeline.require_ready_for_downstream(model, "gateway")
    if gate_err is not None:
        return validation_error(gate_err)

    slug, already, _visibility = benchmark_launch.start_run(benchmark_key, model)
    return accepted(
        slug,
        url_for("benchmarks_api.benchmark_status", slug=slug),
        already_running=already,
    )
