"""
Launch public benchmark runs from the browser.

Mirrors eval_launch.py: argv subprocess, Docker via docker_launch. Models are
either gateway-allowlisted ids or a custom Hugging Face repo served by an
OpenAI-compatible endpoint (local vLLM / DCC node). One in-flight run per
(benchmark, model, base_url) combo.
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

from frontend import docker_launch
from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).resolve().parent.parent
BENCHMARKS_DIR = ROOT / "benchmarks"
RESULTS_DIR = BENCHMARKS_DIR / "results"
RUNNER = BENCHMARKS_DIR / "run_benchmark.py"

sys.path.insert(0, str(BENCHMARKS_DIR))
from benchmarks.run_benchmark import BENCHMARKS, predict_stem  # noqa: E402

_CANDIDATE_CATEGORIES = frozenset({"general_chat", "codex", "research"})

# Custom (non-gateway) models: a Hugging Face repo id served by an
# OpenAI-compatible endpoint (local vLLM, DCC node, etc.). The repo id is
# validated like the scanner's, and the base URL is restricted to internal /
# private hosts so the form can't be used to make the server reach arbitrary
# public addresses (SSRF guard).
_HF_REPO_RE = re.compile(r"^(?:[a-zA-Z0-9][a-zA-Z0-9._-]*/)?[a-zA-Z0-9][a-zA-Z0-9._-]+$")
_INTERNAL_HOST_SUFFIXES = (".duke.edu", ".local", ".internal")
_DEFAULT_CUSTOM_API_KEY = "local-vllm"

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


def validate_custom_model(model: str) -> str | None:
    """Validate a free-text Hugging Face repo id (e.g. ``Qwen/Qwen3-0.6B``)."""
    model = model.strip()
    if not model or len(model) > 200:
        return "enter a Hugging Face repo id (e.g. Qwen/Qwen3-0.6B)"
    if ".." in model or model.startswith(("/", "\\")):
        return "invalid repo id"
    if not _HF_REPO_RE.match(model):
        return "use org/model or a single repo name (letters, digits, . _ -)"
    return None


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


def validate_launch(
    benchmark_key: str,
    model: str,
    *,
    base_url: str | None = None,
) -> str | None:
    if benchmark_key not in BENCHMARKS:
        return f"unknown benchmark: {benchmark_key!r}"
    if base_url:
        # Custom model: free-text HF repo id served by an OpenAI-compatible URL.
        err = validate_custom_model(model)
        if err:
            return err
        err = validate_base_url(base_url)
        if err:
            return err
    elif model not in candidate_models():
        return f"model not in allowlist: {model!r}"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("benchmarks")
    return None


def build_command(
    benchmark_key: str,
    model: str,
    stem: str,
    *,
    extra_env: dict[str, str] | None = None,
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
    if docker_launch.use_docker():
        return docker_launch.compose_run_argv(
            "benchmarks", inner, extra_env=extra_env or None
        )
    return [sys.executable, str(RUNNER), *inner[2:]]


def start_run(
    benchmark_key: str,
    model: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> tuple[str, bool]:
    combo = (benchmark_key, model, (base_url or "").strip())
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

        extra_env = _custom_env(base_url, api_key) if base_url else {}
        cmd = build_command(benchmark_key, model, stem, extra_env=extra_env)

        # Host mode reads the endpoint from the subprocess env; Docker mode gets
        # it via the compose `-e` flags built into the command above.
        proc_env = os.environ.copy()
        proc_env.update(extra_env)

        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {' '.join(cmd)} ===\n".encode())
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT if docker_launch.use_docker() else BENCHMARKS_DIR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=proc_env,
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
