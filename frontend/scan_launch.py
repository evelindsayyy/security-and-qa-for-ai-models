"""Launch HF artifact scans from the browser (mirrors ``eval_launch.py`` pattern)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from frontend import docker_launch
from frontend.output_dirs import OutputDirError, ensure_writable_dir, prepare_output_dir
from frontend.path_safety import is_safe_slug
from scanner.paths import safe_dir_name

ROOT = Path(__file__).parent.parent
SCAN_OUTPUT = ROOT / "scanner" / "output"
DOCKER_COMPOSE_FILE = ROOT / "scanner" / "docker" / "compose.yml"

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()

load_dotenv(ROOT / ".env", override=False)

SUGGESTED_HF_REPOS: tuple[str, ...] = (
    "gpt2",
    "distilbert-base-uncased",
    "facebook/opt-125m",
    "google/flan-t5-small",
    "microsoft/phi-2",
    "BAAI/bge-small-en-v1.5",
    "scan-test--supply-chain-demo",
    "neimasilk/modelscan-extension-mismatch-poc",
)

_HF_REPO_RE = re.compile(r"^(?:[a-zA-Z0-9][a-zA-Z0-9._-]*/)?[a-zA-Z0-9][a-zA-Z0-9._-]+$")


def _output_dir_for_slug(slug: str) -> Path:
    return SCAN_OUTPUT / slug


def _clear_registry_for_slug(slug: str) -> None:
    _RUNNING.pop(slug, None)
    for key, mapped in list(_INFLIGHT.items()):
        if mapped == slug:
            _INFLIGHT.pop(key, None)


def _write_scan_meta(slug: str, hf_repo: str, *, options: dict) -> None:
    meta_path = SCAN_OUTPUT / slug / "scan_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(
            {
                "hf_repo": hf_repo,
                "slug": slug,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "options": options,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _existing_scan_slugs() -> set[str]:
    if not SCAN_OUTPUT.is_dir():
        return set()
    slugs: set[str] = set()
    for p in SCAN_OUTPUT.iterdir():
        if not p.is_dir():
            continue
        if (p / "scan_result.json").is_file() or (p / "scan_run.log").is_file():
            slugs.add(p.name)
    return slugs


def _normalize_hf_repo(hf_repo: str) -> str:
    return hf_repo.strip()


def validate_launch(
    hf_repo: str,
    *,
    skip_modelscan: bool = False,
    skip_fickling: bool = False,
    skip_modelaudit: bool = False,
    skip_deps: bool = False,
    skip_secrets: bool = False,
) -> str | None:
    hf_repo = _normalize_hf_repo(hf_repo)
    if not hf_repo or len(hf_repo) > 200:
        return "enter a Hugging Face repo id (e.g. gpt2 or org/model)"
    if ".." in hf_repo or hf_repo.startswith(("/", "\\")):
        return "invalid repo id"
    if not _HF_REPO_RE.match(hf_repo):
        return "use org/model or a single repo name (letters, digits, . _ -)"
    if all((skip_modelscan, skip_fickling, skip_modelaudit, skip_deps, skip_secrets)):
        return "at least one scanner must be enabled"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("scanner")
    slug = safe_dir_name(hf_repo)
    return prepare_output_dir(_output_dir_for_slug(slug))


def build_command(
    hf_repo: str,
    *,
    skip_modelscan: bool = False,
    skip_fickling: bool = False,
    skip_modelaudit: bool = False,
    skip_deps: bool = False,
    skip_secrets: bool = False,
) -> list[str]:
    flags: list[str] = []
    if skip_modelscan:
        flags.append("--skip-modelscan")
    if skip_fickling:
        flags.append("--skip-fickling")
    if skip_modelaudit:
        flags.append("--skip-modelaudit")
    if skip_deps:
        flags.append("--skip-deps")
    if skip_secrets:
        flags.append("--skip-secrets")

    if not docker_launch.use_docker():
        return [sys.executable, "-m", "scanner", "scan", hf_repo, *flags]

    return docker_launch.compose_run_argv(
        "scanner",
        ["python", "-m", "scanner", "scan", hf_repo, *flags],
    )


def start_run(
    hf_repo: str,
    *,
    skip_modelscan: bool = False,
    skip_fickling: bool = False,
    skip_modelaudit: bool = False,
    skip_deps: bool = False,
    skip_secrets: bool = False,
) -> tuple[str, bool]:
    hf_repo = _normalize_hf_repo(hf_repo)
    slug = safe_dir_name(hf_repo)
    combo = (
        hf_repo,
        skip_modelscan,
        skip_fickling,
        skip_modelaudit,
        skip_deps,
        skip_secrets,
    )
    with _LOCK:
        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None and _RUNNING[existing].poll() is None:
            return existing, True

        _clear_registry_for_slug(slug)
        try:
            ensure_writable_dir(_output_dir_for_slug(slug))
        except OutputDirError:
            raise

        if docker_launch.use_docker():
            docker_launch.ensure_stack("scanner")

        log_path = ROOT / "scanner" / "output" / slug / "scan_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _write_scan_meta(
            slug,
            hf_repo,
            options={
                "launch_mode": "docker" if docker_launch.use_docker() else "host",
                "skip_modelscan": skip_modelscan,
                "skip_fickling": skip_fickling,
                "skip_modelaudit": skip_modelaudit,
                "skip_deps": skip_deps,
                "skip_secrets": skip_secrets,
            },
        )
        cmd = build_command(
            hf_repo,
            skip_modelscan=skip_modelscan,
            skip_fickling=skip_fickling,
            skip_modelaudit=skip_modelaudit,
            skip_deps=skip_deps,
            skip_secrets=skip_secrets,
        )
        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {' '.join(cmd)} ===\n".encode())
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
        _RUNNING[slug] = proc
        _INFLIGHT[combo] = slug
        return slug, False


def get_status(slug: str) -> dict:
    if not is_safe_slug(slug):
        return {"status": "not_found", "message": ""}

    result_path = ROOT / "scanner" / "output" / slug / "scan_result.json"
    log_path = ROOT / "scanner" / "output" / slug / "scan_run.log"

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        msg = ""
        if log_path.is_file():
            msg = log_path.read_text(encoding="utf-8", errors="replace")[-500:]
        return {"status": "running", "message": msg}

    if result_path.is_file():
        return {"status": "complete", "message": ""}

    if proc is not None and proc.poll() is not None:
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-800:] if log_path.is_file() else ""
        return {"status": "failed", "message": msg, "hf_repo": _read_hf_repo(slug)}

    if log_path.is_file() and not result_path.is_file():
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-800:]
        if msg.strip():
            return {"status": "failed", "message": msg, "hf_repo": _read_hf_repo(slug)}

    return {"status": "not_found", "message": ""}


def _read_hf_repo(slug: str) -> str | None:
    meta_path = SCAN_OUTPUT / slug / "scan_meta.json"
    if not meta_path.is_file():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("hf_repo")
    except (json.JSONDecodeError, OSError):
        return None


def get_launch_options() -> dict:
    return {
        "suggested_hf_repos": list(SUGGESTED_HF_REPOS),
        "existing_scan_slugs": sorted(_existing_scan_slugs()),
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
        "docker_detail": docker_launch.docker_detail(),
        "compose_file": str(DOCKER_COMPOSE_FILE.relative_to(ROOT)),
    }
