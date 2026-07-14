"""Prepare pillar output directories — wipe stale runs and verify writability."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Longest match first when resolving a path to its pillar output root.
_PILLAR_OUTPUT_ROOTS = (
    "safety/promptfoo/output",
    "safety/garak/output",
    "safety/output",
    "scanner/output",
    "evaluator/results",
    "benchmarks/results",
    "personality/results",
)


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


def _pillar_output_root(path: Path, repo_root: Path = REPO_ROOT) -> Path | None:
    try:
        rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None
    for name in _PILLAR_OUTPUT_ROOTS:
        if rel == name or rel.startswith(f"{name}/"):
            return repo_root / name
    return None


def _format_permission_error(
    path: Path,
    exc: OSError,
    *,
    repo_root: Path = REPO_ROOT,
) -> str:
    mount_root = _pillar_output_root(path, repo_root) or path.parent
    try:
        rel_mount = mount_root.relative_to(repo_root)
        mount_hint = f"$PWD/{rel_mount.as_posix()}"
    except ValueError:
        mount_hint = str(mount_root)
    try:
        rel_target = path.relative_to(mount_root)
        chown_target = (
            "/out" if rel_target == Path(".") else f"/out/{rel_target.as_posix()}"
        )
    except ValueError:
        chown_target = f"/out/{path.name}"
    uid, gid = os.getuid(), os.getgid()
    return (
        f"cannot write to {path}: {exc}. "
        "Output may be root-owned from an old Docker run. "
        f"Without sudo: docker run --rm -v \"{mount_hint}:/out\" -u root busybox "
        f"chown -R {uid}:{gid} {chown_target} "
        f"(or chown the whole tree: /out). "
        f"With sudo: chown -R \"$USER\" {mount_root}"
    )


def _docker_repair_permissions(path: Path, repo_root: Path = REPO_ROOT) -> bool:
    """Best-effort chown via Docker when output is root-owned from an old run."""
    if not shutil.which("docker") or not hasattr(os, "getuid"):
        return False
    mount_root = _pillar_output_root(path, repo_root)
    if mount_root is None:
        mount_root = path.parent
    try:
        rel = path.resolve().relative_to(mount_root.resolve())
        chown_path = "/out" if rel == Path(".") else f"/out/{rel.as_posix()}"
    except ValueError:
        chown_path = f"/out/{path.name}"
    uid, gid = os.getuid(), os.getgid()
    mount = str(mount_root.resolve())
    for target in (chown_path, "/out"):
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{mount}:/out",
                "-u",
                "root",
                "busybox",
                "chown",
                "-R",
                f"{uid}:{gid}",
                target,
            ],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if proc.returncode == 0:
            return True
    return False


def _prepare_writable(path: Path) -> None:
    wipe_dir(path)
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".write_probe"
    probe.write_text("", encoding="utf-8")
    probe.unlink(missing_ok=True)


def ensure_writable_dir(path: Path, *, repo_root: Path = REPO_ROOT) -> None:
    """Wipe *path*, recreate it, and verify the process user can write there."""
    try:
        _prepare_writable(path)
    except OSError as first_exc:
        exc = first_exc
        if _docker_repair_permissions(path, repo_root):
            try:
                _prepare_writable(path)
                return
            except OSError as retry_exc:
                exc = retry_exc
        raise OutputDirError(_format_permission_error(path, exc, repo_root=repo_root)) from exc


def prepare_output_dir(path: Path, *, repo_root: Path = REPO_ROOT) -> str | None:
    """Return a user-facing error message when *path* is not writable, else None."""
    try:
        ensure_writable_dir(path, repo_root=repo_root)
    except OutputDirError as exc:
        return str(exc)
    return None
