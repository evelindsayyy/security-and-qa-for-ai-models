"""File-based run locks for pillar jobs (coordinates UI launchers and CLI)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

LOCK_NAME = "run.lock"
FRONTEND_SOURCE = "frontend_launch"


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
        return _pid_alive(pid)
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
    payload = {
        "pid": int(pid) if pid is not None else os.getpid(),
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


def should_skip_cli_acquire(path: Path | str) -> bool:
    """True when a frontend launcher already holds the lock on the host."""
    data = _read_lock(Path(path))
    return bool(data and data.get("source") == FRONTEND_SOURCE and is_active(path))
