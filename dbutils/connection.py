"""psycopg connect helpers and TTL-cached availability probes."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any


def psycopg_available() -> bool:
    """True when the optional ``db`` dependency group is installed."""
    try:
        import psycopg  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        return False
    return True


def require_psycopg() -> Any:
    """Import psycopg v3 or exit with install instructions."""
    try:
        import psycopg  # type: ignore[import-untyped]
    except ImportError:
        sys.exit("psycopg is required:  re-run uv sync")
    return psycopg


def connect(dsn: str, *, connect_timeout_s: float | None = 30) -> Any:
    """Open a psycopg connection. ``connect_timeout_s=None`` skips the timeout."""
    psycopg = require_psycopg()
    kwargs: dict[str, Any] = {}
    if connect_timeout_s is not None:
        kwargs["connect_timeout"] = int(connect_timeout_s)
    return psycopg.connect(dsn, **kwargs)


class DsnAvailability:
    """Cache whether Postgres answers a connect (for optional UI read paths).

    Probes at most once per ``ttl_s`` so a down database stalls one request
    by ``connect_timeout_s``, not every request.
    """

    def __init__(
        self,
        dsn_getter: Callable[[], str | None],
        *,
        ttl_s: float = 60.0,
        connect_timeout_s: float = 2.0,
    ) -> None:
        self._dsn_getter = dsn_getter
        self._ttl_s = ttl_s
        self._connect_timeout_s = connect_timeout_s
        self._checked_at = 0.0
        self._ok = False

    def available(self) -> bool:
        dsn = self._dsn_getter()
        if not dsn:
            return False
        now = time.monotonic()
        if now - self._checked_at < self._ttl_s:
            return self._ok
        try:
            with connect(dsn, connect_timeout_s=self._connect_timeout_s):
                self._ok = True
        except Exception:
            self._ok = False
        self._checked_at = now
        return self._ok
