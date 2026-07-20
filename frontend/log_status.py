"""Shared helpers for launcher status JSON payloads."""

from __future__ import annotations

from pathlib import Path

from dbutils.log_tail import read_log_tail, read_run_log


def status_message(log_path: Path | str | None, *, failed: bool = False, full: bool = False) -> str:
    """Log text for progress polling (*full* = entire run log up to RUN_LOG_MAX_BYTES)."""
    if full:
        text, _truncated = read_run_log(log_path)
        return text
    # Failed scans need a longer tail — tqdm progress uses \r and the real
    # ERROR line is often past the old 2 KiB window.
    max_bytes = 65536 if failed else 16384
    text = read_log_tail(log_path, max_bytes=max_bytes)
    if not failed:
        return text
    return _prefer_error_lines(text)


def _prefer_error_lines(text: str) -> str:
    """Surface ERROR/Traceback lines when present so the UI is not just tqdm noise."""
    if not text.strip():
        return text
    lines = text.splitlines()
    interesting = [
        ln
        for ln in lines
        if ln.strip().startswith(("ERROR:", "WARNING:", "Traceback", "download preflight"))
        or "DownloadError" in ln
        or "not enough free disk" in ln
        or "timed out" in ln.lower()
        or "HF_TOKEN" in ln
    ]
    if not interesting:
        return text
    # Keep a short context window around the end of the log plus highlighted lines.
    tail = lines[-40:] if len(lines) > 40 else lines
    merged: list[str] = []
    seen: set[str] = set()
    for ln in interesting + ["---"] + tail:
        if ln in seen and ln != "---":
            continue
        seen.add(ln)
        merged.append(ln)
    return "\n".join(merged)


def run_log_payload(log_path: Path | str | None) -> dict[str, str | bool]:
    """Status JSON fields for a live run log."""
    text, truncated = read_run_log(log_path)
    return {"message": text, "log": text, "log_truncated": truncated}
