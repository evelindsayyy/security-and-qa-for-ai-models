"""Launch HF artifact scans from the browser (mirrors ``eval_launch.py`` pattern)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from frontend.path_safety import is_safe_slug
from scanner.paths import safe_dir_name

ROOT = Path(__file__).parent.parent
SCAN_OUTPUT = ROOT / "scanner" / "output"

# Shown as datalist suggestions — any valid HF repo id is accepted.
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

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()


def _wipe_outputs(slug: str) -> None:
    """Delete prior scan outputs for one model slug before a fresh run."""
    target = SCAN_OUTPUT / slug
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


def _existing_scan_slugs() -> set[str]:
    if not SCAN_OUTPUT.is_dir():
        return set()
    return {
        p.name
        for p in SCAN_OUTPUT.iterdir()
        if p.is_dir() and (p / "scan_result.json").is_file()
    }


def _normalize_hf_repo(hf_repo: str) -> str:
    return hf_repo.strip()


def validate_launch(
    hf_repo: str,
    *,
    no_download: bool = False,
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
    return None


def build_command(
    hf_repo: str,
    *,
    no_download: bool = False,
    skip_modelscan: bool = False,
    skip_fickling: bool = False,
    skip_modelaudit: bool = False,
    skip_deps: bool = False,
    skip_secrets: bool = False,
) -> list[str]:
    cmd = [sys.executable, "-m", "scanner", "scan", hf_repo]
    if no_download:
        cmd.append("--no-download")
    if skip_modelscan:
        cmd.append("--skip-modelscan")
    if skip_fickling:
        cmd.append("--skip-fickling")
    if skip_modelaudit:
        cmd.append("--skip-modelaudit")
    if skip_deps:
        cmd.append("--skip-deps")
    if skip_secrets:
        cmd.append("--skip-secrets")
    return cmd


def start_run(
    hf_repo: str,
    *,
    no_download: bool = False,
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
        no_download,
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

        # Fresh run — clear stale outputs so the UI never shows blended results.
        _wipe_outputs(slug)

        log_path = ROOT / "scanner" / "output" / slug / "scan_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as log_f:
            proc = subprocess.Popen(
                build_command(
                    hf_repo,
                    no_download=no_download,
                    skip_modelscan=skip_modelscan,
                    skip_fickling=skip_fickling,
                    skip_modelaudit=skip_modelaudit,
                    skip_deps=skip_deps,
                    skip_secrets=skip_secrets,
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

    result_path = ROOT / "scanner" / "output" / slug / "scan_result.json"
    log_path = ROOT / "scanner" / "output" / slug / "scan_run.log"

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        msg = ""
        if log_path.is_file():
            msg = log_path.read_text(encoding="utf-8", errors="replace")[-500:]
        return {"status": "running", "message": msg}

    if proc is not None and proc.returncode == 0 and result_path.is_file():
        return {"status": "complete", "message": ""}

    if result_path.is_file() and proc is None:
        return {"status": "complete", "message": ""}

    if proc is not None:
        msg = log_path.read_text(encoding="utf-8", errors="replace")[-800:] if log_path.is_file() else ""
        return {"status": "failed", "message": msg}

    return {"status": "not_found", "message": ""}


def get_launch_options() -> dict:
    return {
        "suggested_hf_repos": list(SUGGESTED_HF_REPOS),
        "existing_scan_slugs": sorted(_existing_scan_slugs()),
    }
