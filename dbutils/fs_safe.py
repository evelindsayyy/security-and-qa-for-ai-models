"""Filesystem helpers that degrade on permission errors instead of raising.

Root-owned pillar output dirs from old Docker runs can make ``Path.is_file()`` /
``Path.iterdir()`` raise ``PermissionError``. Call sites that list many sibling
directories must skip unreadable entries rather than crash the whole route.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def is_file(path: Path) -> bool:
    """Like ``Path.is_file()`` but returns False on OSError."""
    try:
        return path.is_file()
    except OSError:
        return False


def is_dir(path: Path) -> bool:
    """Like ``Path.is_dir()`` but returns False on OSError."""
    try:
        return path.is_dir()
    except OSError:
        return False


def iterdir(path: Path) -> Iterator[Path]:
    """Like ``Path.iterdir()`` but skips entries that cannot be stat'd."""
    try:
        entries = list(path.iterdir())
    except OSError:
        return
    for entry in entries:
        try:
            entry.stat()
        except OSError:
            continue
        yield entry


def glob(path: Path, pattern: str) -> Iterator[Path]:
    """Like ``Path.glob(pattern)`` but skips matches that cannot be stat'd."""
    try:
        matches = list(path.glob(pattern))
    except OSError:
        return
    for match in matches:
        try:
            match.stat()
        except OSError:
            continue
        yield match
