"""
Shared "try Postgres, fall back to disk" dispatch used by every pillar's
``get_*_data()`` — a misconfigured or unreachable DSN must never break the
UI, it should just serve from artifacts.
"""

from __future__ import annotations

from typing import Callable


def get_data_with_db_fallback(
    db_available: Callable[[], bool],
    db_fn: Callable[[], dict],
    file_fn: Callable[[], dict],
) -> dict:
    """Call ``db_fn()`` when ``db_available()`` is true; any exception (or
    unavailability) falls back to ``file_fn()``. Returns the dict either
    way so callers can still post-process it uniformly regardless of which
    source produced it."""
    try:
        if db_available():
            return db_fn()
    except Exception:
        pass  # any DB hiccup -> files, never a broken page
    return file_fn()
