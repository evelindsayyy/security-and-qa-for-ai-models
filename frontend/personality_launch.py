"""Launch personality runs (BFI, compass, …) from the browser."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from dbutils import run_lock
from dbutils.run_paths import PRIVATE_SEGMENT
from frontend import docker_launch
from frontend.launch_registry import check_inflight_combo
from frontend.log_status import run_log_payload
from frontend.path_safety import is_safe_slug
from frontend.run_paths import inflight_scope_key
from personality.test_catalog import DEFAULT_TEST_KEY, get_test, validate_test_key

ROOT = Path(__file__).resolve().parent.parent
PERSONALITY_DIR = ROOT / "personality"
RESULTS_DIR = PERSONALITY_DIR / "results"
RUNNER = PERSONALITY_DIR / "run_personality.py"
# Path of the results tree inside the personality Compose service.
_DOCKER_RESULTS = "/app/personality/results"

_CANDIDATE_CATEGORIES = frozenset({"general_chat", "codex", "research"})

_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
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


def validate_launch(model: str, test_key: str = DEFAULT_TEST_KEY) -> str | None:
    err = validate_test_key(test_key)
    if err:
        return err
    if model not in candidate_models():
        return f"model not in allowlist: {model!r}"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("personality")
    return None


def predict_stem(model: str, test_key: str = DEFAULT_TEST_KEY) -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model.strip())[:80] or "model"
    return f"{ts}_{test_key}_{slug}"


def _results_root(*, visibility: str = "public", owner_user_id: str | None = None) -> Path:
    """Host path for flat JSON / log / progress / locks for one view."""
    if visibility == "private" and owner_user_id:
        return RESULTS_DIR / PRIVATE_SEGMENT / owner_user_id
    return RESULTS_DIR


def _docker_output_dir(*, visibility: str, owner_user_id: str | None) -> str:
    if visibility == "private" and owner_user_id:
        return f"{_DOCKER_RESULTS}/{PRIVATE_SEGMENT}/{owner_user_id}"
    return _DOCKER_RESULTS


def build_command(
    model: str,
    stem: str,
    test_key: str = DEFAULT_TEST_KEY,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> list[str]:
    if docker_launch.use_docker():
        out_dir = _docker_output_dir(visibility=visibility, owner_user_id=owner_user_id)
    else:
        out_dir = str(_results_root(visibility=visibility, owner_user_id=owner_user_id))
    inner = [
        "python",
        "run_personality.py",
        "--test",
        test_key,
        "--model",
        model,
        "--output-stem",
        stem,
        "--output-dir",
        out_dir,
    ]
    if docker_launch.use_docker():
        return docker_launch.compose_run_argv("personality", inner)
    return [sys.executable, str(RUNNER), *inner[2:]]


def _run_lock_path(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> Path:
    return _results_root(visibility=visibility, owner_user_id=owner_user_id) / f"{slug}.lock"


def _watch_process(stem: str, proc: subprocess.Popen, lock_path: Path) -> None:
    proc.wait()
    run_lock.release(lock_path)
    with _LOCK:
        if _RUNNING.get(stem) is proc:
            _RUNNING.pop(stem, None)
        for key, slug in list(_INFLIGHT.items()):
            if slug == stem:
                _INFLIGHT.pop(key, None)


def start_run(model: str, test_key: str = DEFAULT_TEST_KEY) -> tuple[str, bool, str]:
    """Returns (stem, was_already_running, visibility)."""
    from frontend.run_launch import build_launch_plan, persist_run_meta_dir

    err = validate_test_key(test_key)
    if err:
        raise ValueError(err)
    spec = get_test(test_key)

    plan = build_launch_plan("personality", model=model, test_key=test_key)
    combo = (test_key, model, *inflight_scope_key(plan.visibility, plan.owner_user_id))
    with _LOCK:
        existing = check_inflight_combo(_RUNNING, _INFLIGHT, combo)
        if existing:
            return existing, True, plan.visibility

        if docker_launch.use_docker():
            docker_launch.ensure_stack("personality")

        stem = predict_stem(model, test_key)
        out_root = _results_root(visibility=plan.visibility, owner_user_id=plan.owner_user_id)
        out_root.mkdir(parents=True, exist_ok=True)
        lock_file = out_root / f"{stem}.lock"
        persist_run_meta_dir(out_root / stem, plan)
        log_path = out_root / f"{stem}.log"
        progress_path = out_root / f"{stem}.progress.json"

        sys.path.insert(0, str(ROOT / "benchmarks"))
        from benchmark_progress import write_progress_stub  # noqa: E402

        write_progress_stub(
            progress_path,
            benchmark_key=test_key,
            benchmark_label=spec["progress_label"],
            model=model,
            total=spec["total_items"],
            unit="items",
        )

        cmd = build_command(
            model,
            stem,
            test_key,
            visibility=plan.visibility,
            owner_user_id=plan.owner_user_id,
        )
        cmd_str = " ".join(cmd)
        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {cmd_str} ===\n".encode())
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUNBUFFERED", "1")
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT if docker_launch.use_docker() else PERSONALITY_DIR),
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
            return stem, True, plan.visibility
        _RUNNING[stem] = proc
        _INFLIGHT[combo] = stem
        threading.Thread(
            target=_watch_process,
            args=(stem, proc, lock_file),
            daemon=True,
        ).start()
        return stem, False, plan.visibility


def _candidate_roots(
    *, visibility: str = "public", owner_user_id: str | None = None
) -> list[Path]:
    """Roots to probe for status — preferred scope first, then legacy flat tree."""
    preferred = _results_root(visibility=visibility, owner_user_id=owner_user_id)
    roots = [preferred]
    if preferred != RESULTS_DIR:
        roots.append(RESULTS_DIR)
    return roots


def _find_sidecar(
    slug: str,
    suffix: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> Path | None:
    for root in _candidate_roots(visibility=visibility, owner_user_id=owner_user_id):
        path = root / f"{slug}{suffix}"
        if path.is_file():
            return path
    return None


def _with_log(
    status: dict,
    slug: str,
    *,
    visibility: str = "public",
    owner_user_id: str | None = None,
) -> dict:
    log_path = _find_sidecar(
        slug, ".log", visibility=visibility, owner_user_id=owner_user_id
    )
    if log_path is None:
        log_path = RESULTS_DIR / f"{slug}.log"
    payload = run_log_payload(log_path)
    status["log"] = payload["log"]
    status["log_truncated"] = payload["log_truncated"]
    try:
        rel = log_path.resolve().relative_to(RESULTS_DIR.resolve())
        status["log_path"] = f"personality/results/{rel.as_posix()}"
    except ValueError:
        status["log_path"] = f"personality/results/{slug}.log"
    return status


def get_status(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict:
    if not is_safe_slug(slug):
        return {"status": "not_found", "progress": 0, "total": 0, "unit": "items", "message": ""}

    sys.path.insert(0, str(ROOT / "benchmarks"))
    from benchmark_progress import load_progress  # noqa: E402

    progress_path = _find_sidecar(
        slug, ".progress.json", visibility=visibility, owner_user_id=owner_user_id
    )
    prog = load_progress(progress_path) if progress_path else {}
    total = int(prog.get("total") or 0)
    if prog.get("cancelled"):
        return _with_log(
            {
                "status": "cancelled",
                "progress": int(prog.get("progress") or 0),
                "total": total,
                "unit": prog.get("unit") or "items",
                "message": prog.get("message") or "Cancelled",
                "model": prog.get("model") or "",
            },
            slug,
            visibility=visibility,
            owner_user_id=owner_user_id,
        )

    out = _find_sidecar(slug, ".json", visibility=visibility, owner_user_id=owner_user_id)
    # Ignore progress.json mistaken as result
    if out is not None and out.name.endswith(".progress.json"):
        out = None
    progress = int(prog.get("progress") or 0)
    meta = {
        "unit": prog.get("unit") or "items",
        "message": prog.get("message") or "",
        "model": prog.get("model") or "",
    }
    if out is not None:
        return {"status": "complete", "progress": total, "total": total, **meta}

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return _with_log(
            {"status": "running", "progress": progress, "total": total, **meta},
            slug,
            visibility=visibility,
            owner_user_id=owner_user_id,
        )
    if proc is not None:
        return _with_log(
            {"status": "failed", "progress": progress, "total": total, **meta},
            slug,
            visibility=visibility,
            owner_user_id=owner_user_id,
        )
    lock_path = _run_lock_path(slug, visibility=visibility, owner_user_id=owner_user_id)
    if progress_path is not None and total and progress < total:
        if run_lock.is_active(lock_path) or run_lock.is_active(RESULTS_DIR / f"{slug}.lock"):
            return _with_log(
                {"status": "running", "progress": progress, "total": total, **meta},
                slug,
                visibility=visibility,
                owner_user_id=owner_user_id,
            )
        return _with_log(
            {"status": "failed", "progress": progress, "total": total, **meta},
            slug,
            visibility=visibility,
            owner_user_id=owner_user_id,
        )
    if _find_sidecar(slug, ".log", visibility=visibility, owner_user_id=owner_user_id):
        return _with_log(
            {"status": "failed", "progress": progress, "total": total, **meta},
            slug,
            visibility=visibility,
            owner_user_id=owner_user_id,
        )
    return {"status": "not_found", "progress": 0, "total": total, "unit": "items", "message": ""}


def cancel_run(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> str | None:
    if not is_safe_slug(slug):
        return f"invalid slug: {slug!r}"
    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        try:
            if proc.pid:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError, PermissionError):
            proc.terminate()
    sys.path.insert(0, str(ROOT / "benchmarks"))
    from benchmark_progress import mark_cancelled  # noqa: E402

    progress_path = _find_sidecar(
        slug, ".progress.json", visibility=visibility, owner_user_id=owner_user_id
    )
    if progress_path is not None:
        mark_cancelled(progress_path, message="Cancelled")
    return None


def get_launch_options() -> dict:
    from personality.test_catalog import DEFAULT_TEST_KEY, TESTS

    return {
        "models": candidate_models(),
        "docker_available": docker_launch.docker_available(),
        "tests": [
            {"key": key, "label": spec["label"], "total_items": spec["total_items"]}
            for key, spec in TESTS.items()
        ],
        "default_test_key": DEFAULT_TEST_KEY,
    }
