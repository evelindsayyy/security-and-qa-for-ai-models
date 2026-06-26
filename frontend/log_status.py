"""Shared helpers for launcher status JSON payloads."""

from __future__ import annotations

from pathlib import Path

from dbutils.log_tail import read_log_tail


def status_message(log_path: Path | str | None, *, failed: bool = False) -> str:
    """Tail of a run log for progress polling."""
    max_bytes = 2048 if failed else 16384
    return read_log_tail(log_path, max_bytes=max_bytes)
