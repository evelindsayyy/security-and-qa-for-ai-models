"""File-based run locks for pillar jobs (coordinates UI launchers and CLI)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

LOCK_NAME = "run.lock"
FRONTEND_SOURCE = "frontend_launch"
# After Flask/web restart the lock PID is often dead (different PID namespace) while
# the docker compose job keeps writing logs on the host. Treat recent log
# activity without a completion artifact as still in flight.
_ORPHAN_LOG_FRESH_SEC = 45 * 60
_DONE_MARKERS = (
    "scan_result.json",
    "merged_safety_result.json",
)


class RunLockError(RuntimeError):
    """Raised when another scan/safety job holds the output lock."""


def lock_path(output_dir: Path | str) -> Path:
    return Path(output_dir) / LOCK_NAME


def _read_lock(path: Path) -> dict[str, Any] | None:
    from dbutils import fs_safe

    if not fs_safe.is_file(path):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def pid_alive(pid: int) -> bool:
    """True when *pid* appears to refer to a live process."""
    return _pid_alive(pid)


def _completion_present(lock_file: Path) -> bool:
    parent = lock_file.parent
    for name in _DONE_MARKERS:
        if (parent / name).is_file():
            return True
    # Flat locks: ``{stem}.run.lock`` beside ``{stem}.json`` / ``.jsonl``
    name = lock_file.name
    if name.endswith(".run.lock"):
        stem = name[: -len(".run.lock")]
        for ext in (".json", ".jsonl"):
            candidate = parent / f"{stem}{ext}"
            if not candidate.is_file():
                continue
            # Benchmarks: incomplete progress still means running
            progress = parent / f"{stem}.progress.json"
            if progress.is_file():
                try:
                    prog = json.loads(progress.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    prog = {}
                total = int(prog.get("total") or 0)
                done = int(prog.get("progress") or 0)
                if total and done < total and not prog.get("cancelled"):
                    return False
                return True
            # Eval writes a growing .jsonl during the run — presence alone is
            # not completion. Rely on lock release / stale-log cleanup.
            if ext == ".jsonl":
                return False
            return True
    return False


def _recent_log_activity(lock_file: Path) -> bool:
    parent = lock_file.parent
    name = lock_file.name
    candidates: list[Path] = [
        parent / "scan_run.log",
        parent / "run.log",
    ]
    if name.endswith(".run.lock"):
        stem = name[: -len(".run.lock")]
        candidates.append(parent / f"{stem}.log")
    now = time.time()
    for path in candidates:
        try:
            if path.is_file() and (now - path.stat().st_mtime) <= _ORPHAN_LOG_FRESH_SEC:
                return True
        except OSError:
            continue
    return False


def _frontend_orphan_active(lock_file: Path) -> bool:
    """True when the launcher PID died but the job still appears to be running."""
    if _completion_present(lock_file):
        return False
    return _recent_log_activity(lock_file)


def is_active(path: Path | str) -> bool:
    """True when the lock file exists and the holder appears to be running."""
    from dbutils import fs_safe

    p = Path(path)
    data = _read_lock(p)
    if not data:
        if fs_safe.is_file(p):
            p.unlink(missing_ok=True)
        return False
    pid = int(data.get("pid") or 0)
    if data.get("source") == FRONTEND_SOURCE:
        if _pid_alive(pid):
            return True
        # Web container restart: PID gone, docker job may still be writing logs.
        if _frontend_orphan_active(p):
            return True
        p.unlink(missing_ok=True)
        return False
    if _pid_alive(pid):
        return True
    p.unlink(missing_ok=True)
    return False


def try_acquire(
    path: Path | str,
    *,
    pid: int | None = None,
    command: str = "",
    source: str = "cli",
) -> bool:
    """Create a lock file atomically. Returns False if another run holds it."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if is_active(p):
        return False
    p.unlink(missing_ok=True)
    try:
        lock_pid = int(pid) if pid is not None else os.getpid()
    except (TypeError, ValueError):
        # Unit tests often pass a Mock Popen without a numeric .pid.
        lock_pid = os.getpid()
    payload = {
        "pid": lock_pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "command": command,
        "source": source,
    }
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    try:
        os.write(fd, json.dumps(payload, indent=2).encode("utf-8"))
    finally:
        os.close(fd)
    return True


def release(path: Path | str) -> None:
    """Remove the lock file if present."""
    Path(path).unlink(missing_ok=True)


def update_pid(path: Path | str, pid: int) -> None:
    """Rewrite the lock's pid after claiming it with a placeholder.

    Lets a caller call try_acquire() (closing the race window against other
    claimants) before the real holder — e.g. a not-yet-spawned subprocess —
    has a pid. Once it does, this fixes up the stored pid so later liveness
    checks (is_active -> _pid_alive) track the actual job, not the request
    thread that claimed the lock on its behalf."""
    p = Path(path)
    data = _read_lock(p) or {}
    data["pid"] = int(pid)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def should_skip_cli_acquire(path: Path | str) -> bool:
    """True when a frontend launcher already holds the lock on the host."""
    data = _read_lock(Path(path))
    return bool(data and data.get("source") == FRONTEND_SOURCE and is_active(path))
