"""Write live progress for in-flight benchmark runs (frontend polling)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _progress_path() -> Path | None:
    raw = os.environ.get("BENCHMARK_PROGRESS_PATH")
    return Path(raw) if raw else None


def write_progress_stub(
    path: Path,
    *,
    benchmark_key: str,
    benchmark_label: str,
    model: str,
    total: int,
    unit: str,
    message: str = "Starting…",
) -> None:
    """Create an initial progress file before the runner subprocess starts."""
    _write(
        path,
        {
            "benchmark": benchmark_key,
            "benchmark_label": benchmark_label,
            "model": model,
            "progress": 0,
            "total": max(0, int(total)),
            "unit": unit,
            "message": message,
            "updated_at": _now(),
        },
    )


def init_progress(*, total: int, unit: str | None = None, message: str = "Running…") -> None:
    """Set or refresh total once the runner knows the dataset size."""
    path = _progress_path()
    if path is None:
        return
    current = _read(path)
    _write(
        path,
        {
            **current,
            "progress": int(current.get("progress", 0)),
            "total": max(0, int(total)),
            "unit": unit or current.get("unit") or "items",
            "message": message,
            "updated_at": _now(),
        },
    )


def tick(*, step: int = 1, message: str | None = None) -> None:
    """Advance progress by *step* (default one item completed)."""
    path = _progress_path()
    if path is None:
        return
    data = _read(path)
    data["progress"] = int(data.get("progress", 0)) + step
    if message is not None:
        data["message"] = message
    data["updated_at"] = _now()
    _write(path, data)


def set_message(message: str) -> None:
    path = _progress_path()
    if path is None:
        return
    data = _read(path)
    data["message"] = message
    data["updated_at"] = _now()
    _write(path, data)


def load_progress(path: Path) -> dict[str, Any]:
    """Read progress JSON for the frontend (missing file → empty dict)."""
    if not path.is_file():
        return {}
    return _read(path)


def mark_cancelled(path: Path, *, message: str = "Cancelled by user") -> None:
    """Record that a run was stopped from the UI."""
    data = _read(path) if path.is_file() else {}
    data["cancelled"] = True
    data["message"] = message
    data["updated_at"] = _now()
    _write(path, data)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
