"""Launch HF artifact scans from the browser (mirrors ``eval_launch.py`` pattern)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

from dbutils import run_lock
from frontend import docker_launch, run_paths
from frontend.log_status import run_log_payload, status_message
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
    """The shared staging directory every scan of *slug* writes to while
    running, regardless of visibility — see frontend.run_paths for why
    private results are relocated out of here only *after* completion."""
    return SCAN_OUTPUT / slug


def _private_scan_dir(slug: str, owner_user_id: str) -> Path:
    return run_paths.scoped_dir(
        _output_dir_for_slug(slug), visibility="private", owner_user_id=owner_user_id
    )


def _finalize_private_scan(slug: str, owner_user_id: str) -> Path:
    """Move a just-completed staging result into its private location.

    Idempotent — safe to call repeatedly (e.g. from concurrent status polls).
    """
    staging = _output_dir_for_slug(slug)
    private_dir = _private_scan_dir(slug, owner_user_id)
    with _LOCK:
        if (private_dir / "scan_result.json").is_file() or not (staging / "scan_result.json").is_file():
            return private_dir
        private_dir.mkdir(parents=True, exist_ok=True)
        for name in ("scan_result.json", "scan_run.log", "scan_meta.json", "run_meta.json"):
            src = staging / name
            if src.is_file():
                shutil.move(str(src), str(private_dir / name))
    return private_dir


def _run_lock_path(slug: str) -> Path:
    return run_lock.lock_path(_output_dir_for_slug(slug))


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


def _existing_scan_slugs(*, visibility: str = "public", owner_user_id: str | None = None) -> set[str]:
    """Slugs with a completed result **in the given scope only** — the
    public catalog, or this one owner's private record. Never both."""
    if visibility == "private":
        if not owner_user_id or not SCAN_OUTPUT.is_dir():
            return set()
        private_root = SCAN_OUTPUT / run_paths.PRIVATE_SEGMENT / owner_user_id
        if not private_root.is_dir():
            return set()
        return {
            p.name
            for p in private_root.iterdir()
            if p.is_dir() and (p / "scan_result.json").is_file()
        }
    if not SCAN_OUTPUT.is_dir():
        return set()
    slugs: set[str] = set()
    for p in SCAN_OUTPUT.iterdir():
        if not p.is_dir() or p.name == run_paths.PRIVATE_SEGMENT:
            continue
        if (p / "scan_result.json").is_file() or (p / "scan_run.log").is_file():
            slugs.add(p.name)
    return slugs


def inflight_scan_slugs() -> set[str]:
    """Slugs with an active run.lock or in-memory subprocess.

    A scan's staging directory is shared regardless of visibility — only one
    scan of a given model can physically run at a time, public or private —
    so this check is intentionally scope-agnostic.
    """
    slugs: set[str] = set()
    if SCAN_OUTPUT.is_dir():
        for p in SCAN_OUTPUT.iterdir():
            if not p.is_dir() or p.name == run_paths.PRIVATE_SEGMENT:
                continue
            if run_lock.is_active(run_lock.lock_path(p)):
                slugs.add(p.name)
    with _LOCK:
        for slug, proc in _RUNNING.items():
            if proc.poll() is None:
                slugs.add(slug)
    return slugs


def _normalize_hf_repo(hf_repo: str) -> str:
    return hf_repo.strip()


def is_scan_inflight(hf_repo: str) -> bool:
    slug = safe_dir_name(_normalize_hf_repo(hf_repo))
    if run_lock.is_active(_run_lock_path(slug)):
        return True
    proc = _RUNNING.get(slug)
    return proc is not None and proc.poll() is None


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
    if is_scan_inflight(hf_repo):
        return f"a scan for {hf_repo!r} is already running — wait for it to finish or open the progress page"
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


def _watch_process(slug: str, proc: subprocess.Popen, lock_path: Path) -> None:
    proc.wait()
    run_lock.release(lock_path)
    with _LOCK:
        if _RUNNING.get(slug) is proc:
            _RUNNING.pop(slug, None)


def start_run(
    hf_repo: str,
    *,
    skip_modelscan: bool = False,
    skip_fickling: bool = False,
    skip_modelaudit: bool = False,
    skip_deps: bool = False,
    skip_secrets: bool = False,
) -> tuple[str, bool, str]:
    """Returns (slug, already_running, visibility) — callers need visibility
    to redirect to the correctly-scoped URL, even while still in progress."""
    from frontend.run_launch import build_launch_plan, persist_run_meta_scan, reused_slug

    hf_repo = _normalize_hf_repo(hf_repo)
    plan = build_launch_plan(
        "scan",
        hf_repo=hf_repo,
        skip_modelscan=skip_modelscan,
        skip_fickling=skip_fickling,
        skip_modelaudit=skip_modelaudit,
        skip_deps=skip_deps,
        skip_secrets=skip_secrets,
    )
    if plan.reused:
        slug = reused_slug(plan) or safe_dir_name(hf_repo)
        return slug, True, plan.visibility

    slug = safe_dir_name(hf_repo)
    combo = (
        hf_repo,
        skip_modelscan,
        skip_fickling,
        skip_modelaudit,
        skip_deps,
        skip_secrets,
    )
    lock_file = _run_lock_path(slug)

    with _LOCK:
        if is_scan_inflight(hf_repo):
            return slug, True, plan.visibility

        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None and _RUNNING[existing].poll() is None:
            return existing, True, plan.visibility

        _clear_registry_for_slug(slug)
        try:
            ensure_writable_dir(_output_dir_for_slug(slug))
        except OutputDirError:
            raise

        if docker_launch.use_docker():
            docker_launch.ensure_stack("scanner")

        log_path = ROOT / "scanner" / "output" / slug / "scan_run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_command(
            hf_repo,
            skip_modelscan=skip_modelscan,
            skip_fickling=skip_fickling,
            skip_modelaudit=skip_modelaudit,
            skip_deps=skip_deps,
            skip_secrets=skip_secrets,
        )
        cmd_str = " ".join(cmd)

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
        persist_run_meta_scan(_output_dir_for_slug(slug), plan)
        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {cmd_str} ===\n".encode())
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        if not run_lock.try_acquire(
            lock_file,
            pid=proc.pid,
            command=cmd_str,
            source=run_lock.FRONTEND_SOURCE,
        ):
            proc.terminate()
            return slug, True, plan.visibility
        _RUNNING[slug] = proc
        _INFLIGHT[combo] = slug
        threading.Thread(
            target=_watch_process,
            args=(slug, proc, lock_file),
            daemon=True,
        ).start()
        return slug, False, plan.visibility


def get_status(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict:
    if not is_safe_slug(slug):
        return {"status": "not_found", "message": ""}

    staging_dir = _output_dir_for_slug(slug)
    staging_result = staging_dir / "scan_result.json"
    staging_log = staging_dir / "scan_run.log"
    staging_rel_log = f"scanner/output/{slug}/scan_run.log"

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return {
            "status": "running",
            "log_path": staging_rel_log,
            **run_log_payload(staging_log),
        }

    if run_lock.is_active(_run_lock_path(slug)) and not staging_result.is_file():
        return {
            "status": "running",
            "log_path": staging_rel_log,
            **run_log_payload(staging_log),
        }

    # A completed run's result may still be sitting in staging (not yet
    # moved) or may already be at its final scoped location — resolve that
    # here so "complete" always reports from wherever it actually lives.
    if visibility == "private" and owner_user_id:
        active_dir = (
            _finalize_private_scan(slug, owner_user_id)
            if staging_result.is_file()
            else _private_scan_dir(slug, owner_user_id)
        )
    else:
        active_dir = staging_dir

    result_path = active_dir / "scan_result.json"
    if result_path.is_file():
        rel_log = str((active_dir / "scan_run.log").relative_to(ROOT))
        return {"status": "complete", "message": "", "log_path": rel_log}

    if proc is not None and proc.poll() is not None:
        return {
            "status": "failed",
            "message": status_message(staging_log, failed=True),
            "hf_repo": _read_hf_repo(slug),
            "log_path": staging_rel_log,
        }

    if staging_log.is_file() and not staging_result.is_file():
        msg = status_message(staging_log, failed=True)
        if msg.strip():
            return {
                "status": "failed",
                "message": msg,
                "hf_repo": _read_hf_repo(slug),
                "log_path": staging_rel_log,
            }

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
    from frontend.read_context import read_context

    view_mode, user_id = read_context()
    return {
        "suggested_hf_repos": list(SUGGESTED_HF_REPOS),
        "existing_scan_slugs": sorted(
            _existing_scan_slugs(visibility=view_mode, owner_user_id=user_id)
        ),
        "inflight_scan_slugs": sorted(inflight_scan_slugs()),
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
        "compose_file": str(DOCKER_COMPOSE_FILE.relative_to(ROOT)),
    }
