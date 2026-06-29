"""Launch gateway safety runs from the browser (mirrors ``eval_launch.py`` pattern)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from dbutils import run_lock
from frontend import docker_launch
from frontend.log_status import status_message
from frontend.output_dirs import OutputDirError, prepare_output_dir
from frontend.path_safety import is_safe_slug
from safety.gateway_ids import normalize_gateway_model_id
from safety.merged_paths import iter_merged_result_paths, merged_result_path

ROOT = Path(__file__).parent.parent
RUN_MODULE = "safety.run"

_OUTPUT_DIRS = (
    ROOT / "safety" / "output",
    ROOT / "safety" / "promptfoo" / "output",
    ROOT / "safety" / "garak" / "output",
)

_VALID_PROFILES = frozenset({"base", "education", "healthcare", "finance", "rag", "agentic"})


def _prepare_output_dirs(slug: str, profile: str) -> str | None:
    for base in (ROOT / "safety" / "output", ROOT / "safety" / "promptfoo" / "output"):
        err = prepare_output_dir(base / slug / profile)
        if err:
            return err
    err = prepare_output_dir(ROOT / "safety" / "garak" / "output" / slug)
    return err


def _wipe_outputs(slug: str, profile: str) -> None:
    err = _prepare_output_dirs(slug, profile)
    if err:
        raise OutputDirError(err)


def _run_lock_path(slug: str, profile: str) -> Path:
    return run_lock.lock_path(ROOT / "safety" / "output" / slug / profile)


_GATEWAY_FALLBACK: tuple[str, ...] = (
    "GPT 4.1 Mini",
    "gpt-5-chat",
    "gpt-5.5",
    "gpt-5-mini",
    "gpt-5-nano",
    "Llama 4 Maverick",
    "Llama 4 Scout",
)

_SAFETY_CATEGORIES = frozenset({"general_chat", "codex", "research"})
_PROBE_RE = re.compile(r"^[a-zA-Z0-9.,_-]+$")

_SUITE_LABELS = {
    "promptfoo_duke_policy_v1": "Duke policy",
    "promptfoo_duke_redteam_v1": "Red-team",
    "garak_subset_v1": "Garak",
}

_LOG_ALERT_MARKERS: tuple[tuple[str, str], ...] = (
    ("ERROR: Garak finished", "Garak failed — see log; merge may continue without Garak."),
    ("ERROR: garak report incomplete", "Garak scan incomplete — see log; merge omits Garak."),
    ("WARNING: Garak failed", "Garak failed — see log; merge may continue without Garak."),
    ("ERROR: red-team failed", "Red-team failed — see log."),
    ("ERROR: export failed", "Export failed — see log."),
)


def _read_lock(lock_file: Path) -> dict | None:
    if not lock_file.is_file():
        return None
    try:
        data = json.loads(lock_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _is_stale_lock(lock_file: Path, log_path: Path, run_key: str) -> bool:
    """True when a lock file outlives the process that should hold it."""
    proc = _RUNNING.get(run_key)
    if proc is not None and proc.poll() is None:
        return False
    if not lock_file.is_file():
        return False
    if log_path.is_file():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if "Complete:" in text:
            return True
        if "ERROR:" in text or "Garak: FAILED" in text:
            return True
    lock = _read_lock(lock_file)
    if not lock:
        return True
    pid = int(lock.get("pid") or 0)
    if pid == 1 and lock.get("source") == "cli" and log_path.is_file():
        try:
            if time.time() - log_path.stat().st_mtime > 300:
                return True
        except OSError:
            pass
    if pid > 1 and not run_lock.pid_alive(pid):
        return True
    return False


def _garak_partial_warning(data: dict) -> str | None:
    garak_tool = (data.get("tool_results") or {}).get("garak_subset_v1") or {}
    garak_meta = garak_tool.get("garak") or {}
    expected = garak_meta.get("expected_modules")
    completed = garak_meta.get("completed_modules")
    if garak_meta.get("report_complete") is False:
        if expected and completed is not None:
            return f"Garak partial ({completed}/{expected} modules)"
        return "Garak partial (incomplete report)"
    if expected and completed is not None and completed < expected:
        return f"Garak partial ({completed}/{expected} modules)"
    return None


def _log_alert(log_path: Path) -> str | None:
    if not log_path.is_file():
        return None
    tail = status_message(log_path, failed=True)
    for marker, message in _LOG_ALERT_MARKERS:
        if marker in tail:
            return message
    return None


def _merged_warnings(merged: Path) -> list[str]:
    if not merged.is_file():
        return []
    try:
        data = json.loads(merged.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    warnings: list[str] = []
    missing = data.get("missing_suites") or []
    warnings.extend(_SUITE_LABELS.get(s, s.replace("_", " ")) for s in missing)
    partial = _garak_partial_warning(data)
    if partial:
        warnings.append(partial)
    return warnings


def _running_payload(log_path: Path, rel_log: str) -> dict:
    payload = {
        "status": "running",
        "message": status_message(log_path),
        "log_path": rel_log,
    }
    alert = _log_alert(log_path)
    if alert:
        payload["alert"] = alert
    return payload


_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()


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
    base = ROOT / "safety" / "output"
    return {slug for _path, slug, _profile in iter_merged_result_paths(base)}


def inflight_safety_keys() -> set[str]:
    """Active runs as ``slug/profile`` keys."""
    keys: set[str] = set()
    base = ROOT / "safety" / "output"
    if base.is_dir():
        for slug_dir in base.iterdir():
            if not slug_dir.is_dir():
                continue
            for profile_dir in slug_dir.iterdir():
                if profile_dir.is_dir() and run_lock.is_active(run_lock.lock_path(profile_dir)):
                    keys.add(f"{slug_dir.name}/{profile_dir.name}")
    with _LOCK:
        for run_key, proc in _RUNNING.items():
            if proc.poll() is None:
                keys.add(run_key)
    return keys


def is_safety_inflight(model: str, profile: str) -> bool:
    slug = normalize_gateway_model_id(model)
    run_key = f"{slug}/{profile}"
    if run_lock.is_active(_run_lock_path(slug, profile)):
        return True
    proc = _RUNNING.get(run_key)
    return proc is not None and proc.poll() is None


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
    if is_safety_inflight(model, redteam_profile):
        return (
            f"a safety run for {model!r} (profile {redteam_profile}) is already running — "
            "wait for it to finish or open the progress page"
        )
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
    inner: list[str] = ["python", "-m", RUN_MODULE]
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
        return ["uv", "run", "python", "-m", RUN_MODULE, *inner[3:]]

    return docker_launch.compose_run_argv(
        "safety",
        inner,
        extra_env={
            "GATEWAY_MODEL": model,
            "REDTEAM_GRADER_MODEL": model,
        },
    )


def _watch_process(run_key: str, proc: subprocess.Popen, lock_path: Path) -> None:
    proc.wait()
    run_lock.release(lock_path)
    with _LOCK:
        if _RUNNING.get(run_key) is proc:
            _RUNNING.pop(run_key, None)


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
    from frontend.run_launch import build_launch_plan, persist_run_meta_dir, reused_run_key

    plan = build_launch_plan(
        "safety",
        force_private=bool(garak_probes) or redteam_profile != "base",
        model=model,
        redteam_profile=redteam_profile,
        skip_policy=skip_policy,
        skip_redteam=skip_redteam,
        skip_garak=skip_garak,
        skip_promptfoo=skip_promptfoo,
        garak_probes=garak_probes,
    )
    if plan.reused:
        run_key = reused_run_key(plan) or f"{normalize_gateway_model_id(model)}/{redteam_profile}"
        return run_key, True

    slug = normalize_gateway_model_id(model)
    run_key = f"{slug}/{redteam_profile}"
    combo = (model, redteam_profile, skip_policy, skip_redteam, skip_garak, skip_promptfoo, garak_probes or "")
    lock_file = _run_lock_path(slug, redteam_profile)

    with _LOCK:
        if is_safety_inflight(model, redteam_profile):
            return run_key, True

        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None and _RUNNING[existing].poll() is None:
            return existing, True

        _wipe_outputs(slug, redteam_profile)

        if docker_launch.use_docker():
            docker_launch.ensure_stack("safety")

        log_path = ROOT / "safety" / "output" / slug / redteam_profile / "run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        persist_run_meta_dir(log_path.parent, plan)
        cmd = build_command(
            model,
            redteam_profile=redteam_profile,
            skip_policy=skip_policy,
            skip_redteam=skip_redteam,
            skip_garak=skip_garak,
            skip_promptfoo=skip_promptfoo,
            garak_probes=garak_probes,
        )
        cmd_str = " ".join(cmd)

        with log_path.open("ab") as log_f:
            log_f.write(f"\n=== UI launch: {cmd_str} ===\n".encode())
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
            return run_key, True
        _RUNNING[run_key] = proc
        _INFLIGHT[combo] = run_key
        threading.Thread(
            target=_watch_process,
            args=(run_key, proc, lock_file),
            daemon=True,
        ).start()
        return run_key, False


def get_status(slug: str, profile: str = "base") -> dict:
    if not is_safe_slug(slug) or not is_safe_slug(profile):
        return {"status": "not_found", "message": ""}

    run_key = f"{slug}/{profile}"
    merged = merged_result_path(ROOT / "safety" / "output", slug, profile)
    log_path = ROOT / "safety" / "output" / slug / profile / "run.log"
    rel_log = f"safety/output/{slug}/{profile}/run.log"
    lock_file = _run_lock_path(slug, profile)

    proc = _RUNNING.get(run_key)
    if proc is not None and proc.poll() is None:
        return _running_payload(log_path, rel_log)

    if run_lock.is_active(lock_file) and not merged.is_file():
        if _is_stale_lock(lock_file, log_path, run_key):
            run_lock.release(lock_file)
            msg = status_message(log_path, failed=True)
            return {"status": "failed", "message": msg, "log_path": rel_log}
        return _running_payload(log_path, rel_log)

    if merged.is_file():
        warnings = _merged_warnings(merged)
        if warnings:
            return {
                "status": "partial",
                "message": "",
                "warnings": warnings,
                "log_path": rel_log,
            }
        return {"status": "complete", "message": "", "log_path": rel_log}

    if proc is not None:
        return {
            "status": "failed",
            "message": status_message(log_path, failed=True),
            "log_path": rel_log,
        }

    if log_path.is_file() and not merged.is_file():
        msg = status_message(log_path, failed=True)
        if "ERROR:" in msg or "failed (exit" in msg:
            return {"status": "failed", "message": msg, "log_path": rel_log}

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
    model_slugs = {mid: normalize_gateway_model_id(mid) for mid in flat}

    return {
        "gateway_groups": groups,
        "gateway_models": flat,
        "gateway_error": gw.get("error"),
        "model_has_results": model_has_results,
        "model_slugs": model_slugs,
        "inflight_safety_keys": sorted(inflight_safety_keys()),
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
