"""
Launch public benchmark runs from the browser.

Mirrors eval_launch.py: allowlisted models + benchmark keys, argv subprocess,
Docker via docker_launch. One in-flight run per (benchmark, model) combo.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

from frontend import docker_launch
from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
RESULTS_DIR = BENCHMARKS_DIR / "results"
RUNNER = BENCHMARKS_DIR / "run_benchmark.py"

sys.path.insert(0, str(BENCHMARKS_DIR))
from benchmarks.run_benchmark import BENCHMARKS, predict_stem  # noqa: E402

_CANDIDATE_CATEGORIES = frozenset({"general_chat", "codex", "research"})

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple[str, str], str] = {}
_LOCK = threading.Lock()


def candidate_models() -> tuple[str, ...]:
    try:
        from gateway.catalog import eligible_models

        ids = eligible_models(_CANDIDATE_CATEGORIES)
    except Exception:  # noqa: BLE001
        ids = []
    if ids:
        return tuple(ids)
    return ("GPT 4.1 Mini", "gpt-5-chat", "Llama 4 Maverick", "Llama 4 Scout")


def validate_launch(benchmark_key: str, model: str) -> str | None:
    if benchmark_key not in BENCHMARKS:
        return f"unknown benchmark: {benchmark_key!r}"
    if model not in candidate_models():
        return f"model not in allowlist: {model!r}"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("benchmarks")
    return None


def build_command(benchmark_key: str, model: str, stem: str) -> list[str]:
    inner = [
        "python",
        "run_benchmark.py",
        "--benchmark",
        benchmark_key,
        "--model",
        model,
        "--output-stem",
        stem,
    ]
    if docker_launch.use_docker():
        return docker_launch.compose_run_argv("benchmarks", inner)
    return [sys.executable, str(RUNNER), *inner[2:]]


def start_run(benchmark_key: str, model: str) -> tuple[str, bool]:
    combo = (benchmark_key, model)
    with _LOCK:
        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None \
                and _RUNNING[existing].poll() is None:
            return existing, True

        if docker_launch.use_docker():
            docker_launch.ensure_stack("benchmarks")

        stem = predict_stem(benchmark_key, model)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RESULTS_DIR / f"{stem}.log"
        cmd = build_command(benchmark_key, model, stem)
        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {' '.join(cmd)} ===\n".encode())
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT if docker_launch.use_docker() else BENCHMARKS_DIR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
        _RUNNING[stem] = proc
        _INFLIGHT[combo] = stem
        return stem, False


def _output_path(stem: str) -> Path | None:
    for ext in (".json", ".jsonl"):
        path = RESULTS_DIR / f"{stem}{ext}"
        if path.is_file():
            return path
    return None


def get_status(slug: str) -> dict:
    if not is_safe_slug(slug):
        return {"status": "not_found", "progress": 0, "total": 1}

    total = 1
    out = _output_path(slug)
    if out is not None:
        return {"status": "complete", "progress": 1, "total": total}

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return {"status": "running", "progress": 0, "total": total}
    if proc is not None:
        return {"status": "failed", "progress": 0, "total": total}
    if (RESULTS_DIR / f"{slug}.log").is_file():
        return {"status": "failed", "progress": 0, "total": total}
    return {"status": "not_found", "progress": 0, "total": total}


def get_launch_options() -> dict:
    models = candidate_models()
    return {
        "benchmarks": [
            {"key": k, "label": v["label"]} for k, v in sorted(BENCHMARKS.items())
        ],
        "models": list(models),
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
    }
