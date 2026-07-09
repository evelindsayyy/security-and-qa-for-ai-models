"""
Shared "try Postgres, fall back to disk" dispatch used by every pillar's
``get_*_data()`` — a misconfigured or unreachable DSN must never break the
UI, it should just serve from artifacts.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

_LAST_DB_ERROR: str | None = None


def last_db_fallback_error() -> str | None:
    """Most recent DB read error that triggered a disk fallback (for diagnostics)."""
    return _LAST_DB_ERROR


def _strict_db() -> bool:
    return os.environ.get("FRONTEND_DB_STRICT", "").strip().lower() in ("1", "true", "yes", "on")


def get_data_with_db_fallback(
    db_available: Callable[[], bool],
    db_fn: Callable[[], dict],
    file_fn: Callable[[], dict],
    *,
    pillar: str = "",
) -> dict:
    """Call ``db_fn()`` when ``db_available()`` is true.

    When Postgres is configured but ``db_fn()`` raises, log the error and fall
    back to disk unless ``FRONTEND_DB_STRICT=1`` (re-raise for debugging).
    """
    global _LAST_DB_ERROR
    label = pillar or "pillar"
    try:
        if db_available():
            try:
                result = db_fn()
                _LAST_DB_ERROR = None
                return result
            except Exception as exc:
                _LAST_DB_ERROR = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "Postgres read failed for %s — falling back to disk: %s",
                    label,
                    _LAST_DB_ERROR,
                    exc_info=True,
                )
                if _strict_db():
                    raise
    except Exception as exc:
        if _strict_db():
            raise
        if not _LAST_DB_ERROR:
            _LAST_DB_ERROR = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "DB availability check failed for %s — falling back to disk: %s",
                label,
                _LAST_DB_ERROR,
            )
    return file_fn()
