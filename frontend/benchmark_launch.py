"""
Launch public benchmark runs from the browser.

Mirrors eval_launch.py: argv subprocess, Docker via docker_launch. Models are
either gateway-allowlisted ids, HF Inference Providers (hosted), or any model
served by a self-hosted OpenAI-compatible API (vLLM, Ollama, your own server).
One in-flight run per (benchmark, model, base_url) combo.
"""

from __future__ import annotations

import ipaddress
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

from dbutils import run_lock
from frontend import docker_launch
from frontend.log_status import run_log_payload
from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
RESULTS_DIR = BENCHMARKS_DIR / "results"
RUNNER = BENCHMARKS_DIR / "run_benchmark.py"

sys.path.insert(0, str(BENCHMARKS_DIR))
from benchmarks.run_benchmark import (  # noqa: E402
    BENCHMARKS,
    _expected_total,
    benchmark_options_schema,
    predict_stem,
)
from benchmarks.benchmark_progress import load_progress, write_progress_stub  # noqa: E402

HOSTED_SAMPLE_MAX = 200
HOSTED_SAMPLE_WARN = 50

_CANDIDATE_CATEGORIES = frozenset({"general_chat", "codex", "research"})

# Custom (self-hosted API): any model id the server's OpenAI-compatible
# ``/v1/chat/completions`` endpoint expects. Base URL is restricted to internal /
# private hosts (SSRF guard).
# Hosted HF Inference Providers: repo id with optional ``:provider`` pin.
_HF_REPO_RE = re.compile(
    r"^(?:[a-zA-Z0-9][a-zA-Z0-9._-]*/)?[a-zA-Z0-9][a-zA-Z0-9._-]+"
    r"(?::[a-zA-Z0-9][a-zA-Z0-9._-]*)?$"
)
_CUSTOM_API_MODEL_RE = re.compile(r"^[\w.\-/+]+$")
_INTERNAL_HOST_SUFFIXES = (".duke.edu", ".local", ".internal")
_DEFAULT_CUSTOM_API_KEY = "local-vllm"  # placeholder for unauthenticated local servers

# Hosted "no-setup" path: Hugging Face Inference Providers exposes an
# OpenAI-compatible router, so users can benchmark a repo with just a token (no
# vLLM/DCC). The base URL is a fixed, server-controlled constant; the matching
# host is allowlisted past the internal-only SSRF guard. Only https is allowed,
# and only this exact host — arbitrary public addresses stay blocked.
HF_INFERENCE_BASE_URL = "https://router.huggingface.co/v1"
_PUBLIC_HOST_ALLOWLIST = ("router.huggingface.co",)

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple[str, str, str], str] = {}
_LOCK = threading.Lock()


def validate_hosted_model(model: str) -> str | None:
    """Validate a Hugging Face repo id for Inference Providers (optional ``:provider`` pin)."""
    model = model.strip()
    if not model or len(model) > 200:
        return "enter a Hugging Face repo id (e.g. Qwen/Qwen3-0.6B)"
    if ".." in model or model.startswith(("/", "\\")):
        return "invalid repo id"
    if not _HF_REPO_RE.match(model):
        return (
            "use org/model (optionally org/model:provider), letters, digits, . _ -"
        )
    return None


def validate_custom_api_model(model: str) -> str | None:
    """Validate the model id sent to a self-hosted OpenAI-compatible API."""
    model = model.strip()
    if not model or len(model) > 200:
        return (
            "enter the model id your API expects "
            "(e.g. my-model, gpt-4, or Qwen/Qwen3-0.6B)"
        )
    if ".." in model or model.startswith(("/", "\\")):
        return "invalid model id"
    if not _CUSTOM_API_MODEL_RE.match(model):
        return "use letters, digits, and . _ - / + only"
    return None


def validate_custom_model(model: str) -> str | None:
    """Backward-compatible alias — prefer :func:`validate_custom_api_model`."""
    return validate_custom_api_model(model)


def _is_internal_host(host: str) -> bool:
    """True if *host* is a private/loopback IP or an internal hostname.

    Public IPs and link-local (cloud metadata, 169.254.0.0/16) are rejected.
    """
    if not host:
        return False
    host = host.strip().strip("[]")  # tolerate bracketed IPv6
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or (ip.is_private and not ip.is_link_local)
    except ValueError:
        pass
    name = host.lower()
    if name == "localhost":
        return True
    if "." not in name:  # bare single-label hostname (e.g. a DCC node)
        return True
    return name.endswith(_INTERNAL_HOST_SUFFIXES)


def validate_base_url(base_url: str) -> str | None:
    """Validate a custom OpenAI-compatible base URL (internal hosts only)."""
    base_url = base_url.strip()
    if not base_url:
        return "enter the model's base URL (e.g. http://<node>:8000/v1)"
    if len(base_url) > 300:
        return "base URL is too long"
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        return "base URL must start with http:// or https://"
    if not parsed.hostname:
        return "base URL is missing a host"
    if parsed.hostname.lower() in _PUBLIC_HOST_ALLOWLIST:
        # Trusted hosted provider (e.g. HF Inference Providers): allow it past
        # the internal-only guard, but require https.
        if parsed.scheme != "https":
            return "hosted provider URL must use https://"
        return None
    if not _is_internal_host(parsed.hostname):
        return (
            "base URL must point at an internal/private host "
            "(localhost, a private IP, or a *.duke.edu / DCC node)"
        )
    return None


def _custom_env(base_url: str, api_key: str | None) -> dict[str, str]:
    """Env overrides so every benchmark script targets the custom endpoint.

    TruthfulQA reads ``TQA_BASE_URL`` ahead of ``LITELLM_BASE_URL`` and
    ``run_benchmark.py`` would otherwise default it to the Duke gateway, so all
    the base-URL / key aliases are set explicitly here.
    """
    base_url = base_url.strip()
    key = (api_key or "").strip() or _DEFAULT_CUSTOM_API_KEY
    return {
        "LITELLM_BASE_URL": base_url,
        "TQA_BASE_URL": base_url,
        "OPENAI_BASE_URL": base_url,
        "OPENAI_API_KEY": key,
        "LITELLM_API_KEY": key,
        "TQA_API_KEY": key,
    }


def candidate_models() -> tuple[str, ...]:
    try:
        from gateway.catalog import eligible_models

        ids = eligible_models(_CANDIDATE_CATEGORIES)
    except Exception:  # noqa: BLE001
        ids = []
    if ids:
        return tuple(ids)
    return ("GPT 4.1 Mini", "gpt-5-chat", "Llama 4 Maverick", "Llama 4 Scout")


def validate_run_options(
    benchmark_key: str,
    sample: int | None,
    seed: int | None,
    *,
    hosted: bool = False,
) -> str | None:
    if benchmark_key not in BENCHMARKS:
        return f"unknown benchmark: {benchmark_key!r}"
    cfg = BENCHMARKS[benchmark_key]
    if sample is not None:
        if sample < 1:
            return "sample size must be at least 1"
        sample_cfg = cfg.get("sample")
        if not sample_cfg:
            return f"{cfg['label']} does not support a custom sample size"
        max_val = int(sample_cfg["max"])
        if hosted:
            max_val = min(max_val, HOSTED_SAMPLE_MAX)
        if sample > max_val:
            return f"sample size cannot exceed {max_val} for {cfg['label']}"
    if seed is not None and "seed" not in cfg:
        return f"{cfg['label']} does not support a random seed"
    return None


def validate_launch(
    benchmark_key: str,
    model: str,
    *,
    base_url: str | None = None,
    sample: int | None = None,
    seed: int | None = None,
) -> str | None:
    if benchmark_key not in BENCHMARKS:
        return f"unknown benchmark: {benchmark_key!r}"
    if base_url == HF_INFERENCE_BASE_URL:
        err = validate_hosted_model(model)
        if err:
            return err
    elif base_url:
        # Self-hosted OpenAI-compatible API (vLLM, Ollama, custom server, DCC, …).
        err = validate_custom_api_model(model)
        if err:
            return err
        err = validate_base_url(base_url)
        if err:
            return err
    elif model not in candidate_models():
        return f"model not in allowlist: {model!r}"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("benchmarks")
    hosted = base_url == HF_INFERENCE_BASE_URL
    return validate_run_options(benchmark_key, sample, seed, hosted=hosted)


def build_command(
    benchmark_key: str,
    model: str,
    stem: str,
    *,
    extra_env: dict[str, str] | None = None,
    sample: int | None = None,
    seed: int | None = None,
) -> list[str]:
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
    if sample is not None:
        inner.extend(["--sample", str(sample)])
    if seed is not None:
        inner.extend(["--seed", str(seed)])
    if docker_launch.use_docker():
        return docker_launch.compose_run_argv(
            "benchmarks", inner, extra_env=extra_env or None
        )
    return [sys.executable, str(RUNNER), *inner[2:]]


def _run_lock_path(stem: str) -> Path:
    """Flat lock file beside {stem}.log — not a subdirectory named after stem."""
    return RESULTS_DIR / f"{stem}.run.lock"


def _watch_process(stem: str, proc: subprocess.Popen, lock_path: Path) -> None:
    proc.wait()
    run_lock.release(lock_path)
    with _LOCK:
        if _RUNNING.get(stem) is proc:
            _RUNNING.pop(stem, None)


def start_run(
    benchmark_key: str,
    model: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    sample: int | None = None,
    seed: int | None = None,
) -> tuple[str, bool]:
    from frontend.run_launch import build_launch_plan, persist_run_meta_dir, reused_slug

    plan = build_launch_plan(
        "benchmark",
        benchmark_key=benchmark_key,
        model=model,
    )
    if plan.reused:
        stem = reused_slug(plan) or predict_stem(benchmark_key, model)
        return stem, True

    combo = (benchmark_key, model, (base_url or "").strip())
    with _LOCK:
        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None \
                and _RUNNING[existing].poll() is None:
            return existing, True

        if docker_launch.use_docker():
            docker_launch.ensure_stack("benchmarks")

        stem = predict_stem(benchmark_key, model)
        lock_file = _run_lock_path(stem)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        persist_run_meta_dir(RESULTS_DIR / stem, plan)
        log_path = RESULTS_DIR / f"{stem}.log"
        progress_path = RESULTS_DIR / f"{stem}.progress.json"

        cfg = BENCHMARKS[benchmark_key]
        sample_cfg = cfg.get("sample") or {}
        write_progress_stub(
            progress_path,
            benchmark_key=benchmark_key,
            benchmark_label=cfg["label"],
            model=model,
            total=_expected_total(cfg, os.environ, sample),
            unit=str(sample_cfg.get("unit", "items")),
        )

        extra_env = _custom_env(base_url, api_key) if base_url else {}
        cmd = build_command(
            benchmark_key,
            model,
            stem,
            extra_env=extra_env,
            sample=sample,
            seed=seed,
        )

        # Host mode reads the endpoint from the subprocess env; Docker mode gets
        # it via the compose `-e` flags built into the command above.
        proc_env = os.environ.copy()
        proc_env.setdefault("PYTHONIOENCODING", "utf-8")
        proc_env.setdefault("PYTHONUNBUFFERED", "1")
        proc_env.update(extra_env)

        cmd_str = " ".join(cmd)
        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {cmd_str} ===\n".encode())
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT if docker_launch.use_docker() else BENCHMARKS_DIR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=proc_env,
                start_new_session=True,
            )
        if not run_lock.try_acquire(
            lock_file,
            pid=proc.pid,
            command=cmd_str,
            source=run_lock.FRONTEND_SOURCE,
        ):
            proc.terminate()
            return stem, True
        _RUNNING[stem] = proc
        _INFLIGHT[combo] = stem
        threading.Thread(
            target=_watch_process,
            args=(stem, proc, lock_file),
            daemon=True,
        ).start()
        return stem, False


def _output_path(stem: str) -> Path | None:
    for ext in (".json", ".jsonl"):
        path = RESULTS_DIR / f"{stem}{ext}"
        if path.is_file():
            return path
    return None


def _progress_path(slug: str) -> Path:
    return RESULTS_DIR / f"{slug}.progress.json"


def is_run_in_progress(slug: str) -> bool:
    """True when a registered subprocess for *slug* is still running."""
    if not is_safe_slug(slug):
        return False
    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return True
    if run_lock.is_active(_run_lock_path(slug)):
        return True
    return False


def _with_log(status: dict, slug: str) -> dict:
    log_path = RESULTS_DIR / f"{slug}.log"
    payload = run_log_payload(log_path)
    status["log"] = payload["log"]
    status["log_truncated"] = payload["log_truncated"]
    status["log_path"] = f"benchmarks/results/{slug}.log"
    return status


def _status_from_progress(slug: str, prog: dict) -> dict:
    progress = int(prog.get("progress") or 0)
    total = int(prog.get("total") or 0)
    return {
        "status": "running",
        "progress": progress,
        "total": total,
        "unit": prog.get("unit") or "items",
        "message": prog.get("message") or "",
        "benchmark": prog.get("benchmark") or "",
        "benchmark_label": prog.get("benchmark_label") or "",
        "model": prog.get("model") or "",
    }


def get_status(slug: str) -> dict:
    if not is_safe_slug(slug):
        return {"status": "not_found", "progress": 0, "total": 0, "unit": "items", "message": ""}

    out = _output_path(slug)
    prog = load_progress(_progress_path(slug))
    progress = int(prog.get("progress") or 0)
    total = int(prog.get("total") or 0)
    unit = prog.get("unit") or "items"
    message = prog.get("message") or ""
    meta = {
        "unit": unit,
        "message": message,
        "benchmark": prog.get("benchmark") or "",
        "benchmark_label": prog.get("benchmark_label") or "",
        "model": prog.get("model") or "",
    }

    if out is not None:
        return {
            "status": "complete",
            "progress": total or progress or 1,
            "total": total or progress or 1,
            **meta,
        }

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        base = _status_from_progress(slug, prog) if prog else {
            "status": "running",
            "progress": progress,
            "total": total,
            **meta,
        }
        return _with_log(base, slug)
    if proc is not None:
        return _with_log({
            "status": "failed",
            "progress": progress,
            "total": total,
            **meta,
        }, slug)
    if _progress_path(slug).is_file() and progress < total:
        # Flask restarted mid-run but the runner is still writing progress.
        if run_lock.is_active(_run_lock_path(slug)):
            return _with_log(_status_from_progress(slug, prog), slug)
        return _status_from_progress(slug, prog)
    if (RESULTS_DIR / f"{slug}.log").is_file():
        return _with_log({
            "status": "failed",
            "progress": progress,
            "total": total,
            **meta,
        }, slug)
    return {"status": "not_found", "progress": 0, "total": 0, "unit": "items", "message": ""}


def get_launch_options() -> dict:
    models = candidate_models()
    return {
        "benchmarks": [
            {"key": k, "label": v["label"]} for k, v in sorted(BENCHMARKS.items())
        ],
        "benchmark_options": benchmark_options_schema(),
        "hosted_sample_max": HOSTED_SAMPLE_MAX,
        "hosted_sample_warn": HOSTED_SAMPLE_WARN,
        "models": list(models),
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
    }
