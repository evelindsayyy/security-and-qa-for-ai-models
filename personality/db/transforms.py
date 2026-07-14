"""
Pure transforms for personality result files — no DB, no frontend imports.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from personality.test_catalog import TESTS

KNOWN_TESTS = frozenset(TESTS)


def _parse_iso_timestamp(value: str | None) -> str | None:
    if not value or value == "—":
        return None
    raw = value.strip()
    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            datetime.fromisoformat(candidate)
            return raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        except ValueError:
            continue
    return None


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def personality_run_row(path: Path) -> dict[str, Any] | None:
    """Parse one personality result JSON into a loader row dict."""
    if path.suffix != ".json" or path.stem.endswith(".progress"):
        return None
    data = read_json_file(path)
    if data is None:
        return None
    test_key = data.get("test")
    if test_key not in KNOWN_TESTS:
        return None
    summary = data.get("summary") or {}
    if not isinstance(summary, dict):
        summary = {}
    traits = summary.get("traits") or {}
    if not isinstance(traits, dict):
        traits = {}
    items = data.get("items") or []
    if not isinstance(items, list):
        items = []
    completed = _parse_iso_timestamp(
        data.get("timestamp") if isinstance(data.get("timestamp"), str) else None
    )
    model = (data.get("model") or "").strip() or "—"
    attempted = summary.get("attempted")
    scored = summary.get("scored")
    coverage = summary.get("coverage")
    n_items = len(items) if items else (int(attempted) if attempted is not None else 0)
    return {
        "output_slug": path.stem,
        "source_filename": path.name,
        "gateway_model_id": model,
        "test_key": test_key,
        "status": "complete",
        "n_items": n_items,
        "attempted": int(attempted) if attempted is not None else None,
        "scored": int(scored) if scored is not None else None,
        "coverage": float(coverage) if coverage is not None else None,
        "traits": traits,
        "items": items,
        "summary": summary,
        "started_at": None,
        "completed_at": completed,
    }
