"""Prepare pillar output directories — wipe stale runs and verify writability."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class OutputDirError(OSError):
    """The current user cannot write to a pillar output path."""


def _rmtree_onerror(func, path, _exc_info) -> None:
    """Retry delete after chmod (helps when the user owns the dir but not all files)."""
    try:
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def wipe_dir(path: Path) -> None:
    """Remove *path* when it exists (best-effort)."""
    if path.is_dir():
        shutil.rmtree(path, onerror=_rmtree_onerror)


def ensure_writable_dir(path: Path) -> None:
    """Wipe *path*, recreate it, and verify the process user can write there."""
    wipe_dir(path)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        parent = path.parent
        uid, gid = os.getuid(), os.getgid()
        raise OutputDirError(
            f"cannot write to {path}: {exc}. "
            "Output may be root-owned from an old Docker run. "
            f'Without sudo: docker run --rm -v "$PWD/{parent}:/out" -u root busybox '
            f"chown -R {uid}:{gid} /out/{path.name} "
            f'(or chown the whole tree: /out). With sudo: chown -R "$USER" {parent}'
        ) from exc


def prepare_output_dir(path: Path) -> str | None:
    """Return a user-facing error message when *path* is not writable, else None."""
    try:
        ensure_writable_dir(path)
    except OutputDirError as exc:
        return str(exc)
    return None
