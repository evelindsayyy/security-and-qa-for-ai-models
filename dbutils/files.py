"""Read pillar JSON artifacts from disk (ingest input)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    """Parse one JSON object. ``None`` on missing, empty, or invalid files."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        data = json.loads(text)
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    """Parse JSONL (one object per line). ``None`` on empty or unreadable files."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except (OSError, json.JSONDecodeError):
        return None
    if not rows:
        return None
    return rows


def iter_files(
    directory: Path,
    pattern: str,
    *,
    exclude_if: Callable[[Path], bool] | None = None,
) -> list[Path]:
    """Sorted paths matching ``pattern`` under ``directory``.

    ``exclude_if`` receives each path; return True to skip (e.g. trace files).
    """
    paths = sorted(directory.glob(pattern))
    if exclude_if is None:
        return paths
    return [p for p in paths if not exclude_if(p)]


def exclude_substrings(*parts: str):
    """Build an ``exclude_if`` that skips paths whose name contains any part."""

    def _exclude(path: Path) -> bool:
        name = path.name
        return any(part in name for part in parts)

    return _exclude
