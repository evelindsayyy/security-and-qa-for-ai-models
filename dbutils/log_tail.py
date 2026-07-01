"""Read trailing portions of log files for UI status polling."""

from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_BYTES = 16384
DEFAULT_MAX_LINES = 200
# Running-job UI: show the full log when possible (long scans/safety runs exceed 16 KiB quickly).
RUN_LOG_MAX_BYTES = 8 * 1024 * 1024


def read_log_tail(
    path: Path | str | None,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Return the tail of a log file, bounded by bytes then line count."""
    text, _truncated = _read_log_bytes(path, max_bytes=max_bytes, max_lines=max_lines)
    return text


def read_run_log(
    path: Path | str | None,
    *,
    max_bytes: int = RUN_LOG_MAX_BYTES,
) -> tuple[str, bool]:
    """Return log text for live run pages — full file when small, else last *max_bytes*."""
    return _read_log_bytes(path, max_bytes=max_bytes, max_lines=None)


def _read_log_bytes(
    path: Path | str | None,
    *,
    max_bytes: int,
    max_lines: int | None,
) -> tuple[str, bool]:
    if not path:
        return "", False
    p = Path(path)
    if not p.is_file():
        return "", False
    try:
        raw = p.read_bytes()
    except OSError:
        return "", False
    if not raw:
        return "", False
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="replace")
    if max_lines is not None:
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            truncated = True
        text = "\n".join(lines)
    if truncated and max_lines is None:
        text = f"[Log truncated — showing last {max_bytes // (1024 * 1024)} MB]\n\n{text}"
    return text, truncated
