"""Read trailing portions of log files for UI status polling."""

from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_BYTES = 16384
DEFAULT_MAX_LINES = 200


def read_log_tail(
    path: Path | str | None,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Return the tail of a log file, bounded by bytes then line count."""
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        raw = p.read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""
    if len(raw) > max_bytes:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return "\n".join(lines)
