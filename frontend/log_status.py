"""Shared helpers for launcher status JSON payloads."""

from __future__ import annotations

from pathlib import Path

from dbutils.log_tail import read_log_tail, read_run_log

# Written by launchers when the child dies via SIGKILL (often OOM).
OOM_KILL_MESSAGE = (
    "ERROR: Scan process was killed by the OS (signal 9 / exit 137) — "
    "likely out of memory while downloading. Retry with SCAN_HF_MAX_WORKERS=1 "
    "(default on low-RAM hosts) or use a smaller HF mirror for artifact scanning."
)

STALL_KILL_MESSAGE = (
    "ERROR: Download stalled (no log progress for {minutes:.0f} minutes; "
    "log quiet ~{age_min:.0f}m). HF transfer may have hung after CDN errors. "
    "Hung scanner was terminated — clear partial weights and retry, or use a "
    "smaller artifact-scan mirror."
)


def is_oom_kill_exit(exit_code: int | None) -> bool:
    """True for SIGKILL (-9) or shell-style 128+9 (137)."""
    if exit_code is None:
        return False
    return exit_code in (-9, 137) or exit_code == 128 + 9


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


def _looks_like_abrupt_download_death(text: str) -> bool:
    """tqdm download progress with no ERROR/Traceback — typical SIGKILL residue."""
    if "ERROR:" in text or "Traceback" in text or "DownloadError" in text:
        return False
    low = text.lower()
    return "fetching" in low or "download preflight" in low or "%|" in text or "it/s" in low


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
        or "out of memory" in ln.lower()
        or "killed by the os" in ln.lower()
        or "download stalled" in ln.lower()
        or "timed out" in ln.lower()
        or "HF_TOKEN" in ln
        or "SCAN_HF_MAX_WORKERS" in ln
    ]
    has_hard_error = any(
        ln.strip().startswith(("ERROR:", "Traceback"))
        or "DownloadError" in ln
        or "killed by the os" in ln.lower()
        or "out of memory" in ln.lower()
        or "download stalled" in ln.lower()
        for ln in lines
    )
    if not interesting:
        if _looks_like_abrupt_download_death(text):
            return f"{OOM_KILL_MESSAGE}\n---\n{text}"
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
    out = "\n".join(merged)
    # Preflight + truncated tqdm with no ERROR is typical of SIGKILL mid-download.
    if not has_hard_error and _looks_like_abrupt_download_death(text):
        return f"{OOM_KILL_MESSAGE}\n{out}"
    return out


def run_log_payload(log_path: Path | str | None) -> dict[str, str | bool]:
    """Status JSON fields for a live run log."""
    text, truncated = read_run_log(log_path)
    return {"message": text, "log": text, "log_truncated": truncated}
