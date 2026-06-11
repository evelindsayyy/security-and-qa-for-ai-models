"""Launch gateway safety runs from the browser (mirrors ``eval_launch.py`` pattern)."""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from pathlib import Path

from frontend.path_safety import is_safe_slug
from safety.gateway_ids import normalize_gateway_model_id

ROOT = Path(__file__).parent.parent
RUN_SCRIPT = ROOT / "safety" / "run_safety.sh"

# Per-slug output dirs wiped before a fresh run so the UI never blends stale
# JSON from a previous run with new results.
_OUTPUT_DIRS = (
    ROOT / "safety" / "output",
    ROOT / "safety" / "promptfoo" / "output",
    ROOT / "safety" / "garak" / "output",
)


def _wipe_outputs(slug: str) -> None:
    """Delete prior safety outputs for one model slug (merged + per-tool)."""
    for base in _OUTPUT_DIRS:
        target = base / slug
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)

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
    from frontend.gateway_catalog import get_gateway_catalog

    gw = get_gateway_catalog()
    ids = [
        m["id"]
        for m in gw.get("models", [])
        if m.get("category") in _SAFETY_CATEGORIES
    ]
    return tuple(ids) if ids else _GATEWAY_FALLBACK


def _existing_safety_slugs() -> set[str]:
    base = ROOT / "safety" / "output"
    if not base.is_dir():
        return set()
    return {
        p.name
        for p in base.iterdir()
        if p.is_dir() and (p / "merged_safety_result.json").is_file()
    }

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()


def validate_launch(
    model: str,
    *,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> str | None:
    if model not in _eligible_gateway_models():
        return f"gateway model not eligible for safety: {model!r}"
    if skip_promptfoo and skip_garak:
        return "cannot skip both promptfoo and garak"
    if garak_probes and not _PROBE_RE.match(garak_probes):
        return "garak_probes: letters, digits, comma, dot, dash, underscore only"
    return None


def build_command(
    model: str,
    *,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> list[str]:
    cmd = ["bash", str(RUN_SCRIPT)]
    if skip_redteam:
        cmd.append("--skip-redteam")
    if skip_garak:
        cmd.append("--skip-garak")
    if skip_promptfoo:
        cmd.append("--skip-promptfoo")
    if garak_probes:
        cmd.extend(["--garak-probes", garak_probes])
    cmd.append(model)
    return cmd


def start_run(
    model: str,
    *,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> tuple[str, bool]:
    slug = normalize_gateway_model_id(model)
    combo = (model, skip_redteam, skip_garak, skip_promptfoo, garak_probes or "")
    with _LOCK:
        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None and _RUNNING[existing].poll() is None:
            return existing, True

        # Fresh run — clear stale outputs so the merge/UI start from a clean slate.
        _wipe_outputs(slug)

        log_path = ROOT / "safety" / "output" / slug / "run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab") as log_f:
            log_f.write(f"\n=== UI launch ===\n".encode())
            proc = subprocess.Popen(
                build_command(
                    model,
                    skip_redteam=skip_redteam,
                    skip_garak=skip_garak,
                    skip_promptfoo=skip_promptfoo,
                    garak_probes=garak_probes,
                ),
                cwd=str(ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )
        _RUNNING[slug] = proc
        _INFLIGHT[combo] = slug
        return slug, False


def get_status(slug: str) -> dict:
    if not is_safe_slug(slug):
        return {"status": "not_found", "message": ""}

    merged = ROOT / "safety" / "output" / slug / "merged_safety_result.json"
    log_path = ROOT / "safety" / "output" / slug / "run.log"

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-600:] if log_path.is_file() else ""
        return {"status": "running", "message": msg}

    if merged.is_file() and proc is not None and proc.returncode == 0:
        return {"status": "complete", "message": ""}

    if merged.is_file() and proc is None:
        return {"status": "complete", "message": ""}

    if proc is not None:
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-800:] if log_path.is_file() else ""
        return {"status": "failed", "message": msg}

    return {"status": "not_found", "message": ""}


def get_launch_options() -> dict:
    from frontend.gateway_catalog import get_gateway_catalog

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
    }
