"""Launch gateway safety runs from the browser (mirrors ``eval_launch.py`` pattern)."""

from __future__ import annotations

import os
import re
import subprocess
import threading
from pathlib import Path

from frontend import docker_launch
from frontend.output_dirs import OutputDirError, prepare_output_dir
from frontend.path_safety import is_safe_slug
from safety.gateway_ids import normalize_gateway_model_id
from safety.merged_paths import iter_merged_result_paths, merged_result_path

ROOT = Path(__file__).parent.parent
RUN_SCRIPT = ROOT / "safety" / "run_safety.sh"

# Per-slug output dirs wiped before a fresh run so the UI never blends stale
# JSON from a previous run with new results.
_OUTPUT_DIRS = (
    ROOT / "safety" / "output",
    ROOT / "safety" / "promptfoo" / "output",
    ROOT / "safety" / "garak" / "output",
)


_VALID_PROFILES = frozenset({"base", "education", "healthcare", "finance", "rag", "agentic"})


def _prepare_output_dirs(slug: str, profile: str) -> str | None:
    """Wipe and verify writability for one (slug, profile) run."""
    for base in (ROOT / "safety" / "output", ROOT / "safety" / "promptfoo" / "output"):
        err = prepare_output_dir(base / slug / profile)
        if err:
            return err
    err = prepare_output_dir(ROOT / "safety" / "garak" / "output" / slug)
    return err


def _wipe_outputs(slug: str, profile: str) -> None:
    """Delete prior safety outputs for one (slug, profile) run."""
    err = _prepare_output_dirs(slug, profile)
    if err:
        raise OutputDirError(err)

# Fallback when the live gateway catalog is unreachable (offline dev).
_GATEWAY_FALLBACK: tuple[str, ...] = (
    "GPT 4.1 Mini",
    "gpt-5-chat",
    "gpt-5.5",
    "gpt-5-mini",
    "gpt-5-nano",
    "Llama 4 Maverick",
    "Llama 4 Scout",
)

# Chat-capable gateway categories — exclude embeddings, audio, etc.
_SAFETY_CATEGORIES = frozenset({"general_chat", "codex", "research"})

_PROBE_RE = re.compile(r"^[a-zA-Z0-9.,_-]+$")


def _eligible_gateway_models() -> tuple[str, ...]:
    from gateway.catalog import get_gateway_catalog

    gw = get_gateway_catalog()
    ids = [
        m["id"]
        for m in gw.get("models", [])
        if m.get("category") in _SAFETY_CATEGORIES
    ]
    return tuple(ids) if ids else _GATEWAY_FALLBACK


def _existing_safety_slugs() -> set[str]:
    """Return slugs that have at least one completed merged result (any profile)."""
    base = ROOT / "safety" / "output"
    return {slug for _path, slug, _profile in iter_merged_result_paths(base)}

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()


def validate_launch(
    model: str,
    *,
    redteam_profile: str = "base",
    skip_policy: bool = False,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> str | None:
    if model not in _eligible_gateway_models():
        return f"gateway model not eligible for safety: {model!r}"
    if redteam_profile not in _VALID_PROFILES:
        return f"unknown profile {redteam_profile!r}; valid: {sorted(_VALID_PROFILES)}"
    if (skip_policy and skip_redteam) and skip_garak:
        return "must run at least one suite"
    if skip_promptfoo and skip_garak:
        return "cannot skip both promptfoo and garak"
    if garak_probes and not _PROBE_RE.match(garak_probes):
        return "garak_probes: letters, digits, comma, dot, dash, underscore only"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("safety")
    slug = normalize_gateway_model_id(model)
    return _prepare_output_dirs(slug, redteam_profile)


def build_command(
    model: str,
    *,
    redteam_profile: str = "base",
    skip_policy: bool = False,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> list[str]:
    inner: list[str] = ["bash", str(RUN_SCRIPT.relative_to(ROOT))]
    inner.extend(["--redteam-profile", redteam_profile])
    if skip_policy:
        inner.append("--skip-policy")
    if skip_redteam:
        inner.append("--skip-redteam")
    if skip_garak:
        inner.append("--skip-garak")
    if skip_promptfoo:
        inner.append("--skip-promptfoo")
    if garak_probes:
        inner.extend(["--garak-probes", garak_probes])
    inner.append(model)

    if not docker_launch.use_docker():
        return ["bash", str(RUN_SCRIPT), *inner[2:]]

    return docker_launch.compose_run_argv(
        "safety",
        inner,
        extra_env={
            "GATEWAY_MODEL": model,
            "REDTEAM_GRADER_MODEL": model,
        },
    )


def start_run(
    model: str,
    *,
    redteam_profile: str = "base",
    skip_policy: bool = False,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> tuple[str, bool]:
    slug = normalize_gateway_model_id(model)
    run_key = f"{slug}/{redteam_profile}"
    combo = (model, redteam_profile, skip_policy, skip_redteam, skip_garak, skip_promptfoo, garak_probes or "")
    with _LOCK:
        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None and _RUNNING[existing].poll() is None:
            return existing, True

        # Fresh run — clear stale outputs for this (slug, profile) pair.
        _wipe_outputs(slug, redteam_profile)

        if docker_launch.use_docker():
            docker_launch.ensure_stack("safety")

        log_path = ROOT / "safety" / "output" / slug / redteam_profile / "run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_command(
            model,
            redteam_profile=redteam_profile,
            skip_policy=skip_policy,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes,
        )
        with log_path.open("ab") as log_f:
            log_f.write(f"\n=== UI launch: {' '.join(cmd)} ===\n".encode())
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
        _RUNNING[run_key] = proc
        _INFLIGHT[combo] = run_key
        return run_key, False


def get_status(slug: str, profile: str = "base") -> dict:
    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return {"status": "not_found", "message": ""}

    run_key = f"{slug}/{profile}"
    merged = merged_result_path(ROOT / "safety" / "output", slug, profile)
    log_path = ROOT / "safety" / "output" / slug / profile / "run.log"

    proc = _RUNNING.get(run_key)
    if proc is not None and proc.poll() is None:
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-600:] if log_path.is_file() else ""
        return {"status": "running", "message": msg}

    if merged.is_file():
        return {"status": "complete", "message": ""}

    if proc is not None:
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-800:] if log_path.is_file() else ""
        return {"status": "failed", "message": msg}

    if log_path.is_file() and not merged.is_file():
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-800:]
        if "ERROR:" in msg or "failed (exit" in msg:
            return {"status": "failed", "message": msg}

    return {"status": "not_found", "message": ""}


def get_launch_options() -> dict:
    from gateway.catalog import get_gateway_catalog

    gw = get_gateway_catalog()
    existing = _existing_safety_slugs()
    groups: list[dict] = []

    for section in gw.get("by_category", []):
        if section["key"] not in _SAFETY_CATEGORIES:
            continue
        models = [m["id"] for m in section["models"]]
        if models:
            groups.append({"label": section["label"], "models": models})

    flat = [m for g in groups for m in g["models"]]
    if not flat:
        flat = list(_GATEWAY_FALLBACK)
        groups = [{"label": "Gateway models", "models": flat}]

    model_has_results = {
        mid: normalize_gateway_model_id(mid) in existing for mid in flat
    }

    return {
        "gateway_groups": groups,
        "gateway_models": flat,
        "gateway_error": gw.get("error"),
        "model_has_results": model_has_results,
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
        "profiles": [
            {"value": "base", "label": "Base (general-purpose baseline)"},
            {"value": "education", "label": "Education (+ teen safety, FERPA probes)"},
            {"value": "healthcare", "label": "Healthcare (+ medical, pharmacy, PHI probes)"},
            {"value": "finance", "label": "Finance (+ insurance, billing, fraud probes)"},
            {"value": "rag", "label": "RAG (+ document exfiltration, poisoning probes)"},
            {"value": "agentic", "label": "Agentic (+ MCP, tool-discovery probes)"},
        ],
    }
