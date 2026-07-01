"""Shared helpers for launcher status JSON payloads."""

from __future__ import annotations

from pathlib import Path

from dbutils.log_tail import read_log_tail, read_run_log


def status_message(log_path: Path | str | None, *, failed: bool = False, full: bool = False) -> str:
    """Log text for progress polling (*full* = entire run log up to RUN_LOG_MAX_BYTES)."""
    if full:
        text, _truncated = read_run_log(log_path)
        return text
    max_bytes = 2048 if failed else 16384
    return read_log_tail(log_path, max_bytes=max_bytes)


def run_log_payload(log_path: Path | str | None) -> dict[str, str | bool]:
    """Status JSON fields for a live run log."""
    text, truncated = read_run_log(log_path)
    return {"message": text, "log": text, "log_truncated": truncated}
