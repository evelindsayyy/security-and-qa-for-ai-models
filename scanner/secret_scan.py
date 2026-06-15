"""
Secret scanning via TruffleHog filesystem mode.

Invokes the official ``trufflehog`` Go binary when available; returns ``None`` or
``available: false`` when the binary is missing (graceful skip, like Trivy spike).

Never stores raw secret values — only redacted output and detector metadata.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

_TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_SKIP_DIR_NAMES = frozenset({".cache", ".git"})


def trufflehog_available() -> bool:
    """Return True if ``trufflehog`` binary is on PATH."""
    return shutil.which("trufflehog") is not None


def _should_skip_path(path: Path, model_dir: Path) -> bool:
    rel_parts = path.relative_to(model_dir).parts
    return any(part in _SKIP_DIR_NAMES or part.startswith(".") for part in rel_parts[:-1])


def _parse_trufflehog_line(line: str) -> dict[str, Any] | None:
    """Parse one NDJSON line from TruffleHog stdout."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _extract_secret_entry(record: dict[str, Any], model_dir: Path) -> dict[str, Any]:
    """Normalize one TruffleHog finding — redacted only."""
    source_meta = record.get("SourceMetadata") or record.get("source_metadata") or {}
    data = source_meta.get("Data") or source_meta.get("data") or {}
    filesystem = data.get("Filesystem") or data.get("filesystem") or {}

    file_path = (
        filesystem.get("file")
        or filesystem.get("path")
        or record.get("SourceID")
        or record.get("source_id")
        or "unknown"
    )
    if isinstance(file_path, str) and str(model_dir) in file_path:
        try:
            file_path = str(Path(file_path).relative_to(model_dir))
        except ValueError:
            file_path = Path(file_path).name

    detector = (
        record.get("DetectorName")
        or record.get("detector_name")
        or record.get("DetectorType")
        or record.get("detector_type")
        or "unknown"
    )
    verified = bool(record.get("Verified") or record.get("verified"))
    redacted = (
        record.get("Redacted")
        or record.get("redacted")
        or record.get("Raw")
        or record.get("raw")
        or "[REDACTED]"
    )
    if redacted and len(str(redacted)) > 80:
        redacted = str(redacted)[:40] + "…[redacted]"

    return {
        "detector": str(detector),
        "file": str(file_path),
        "verified": verified,
        "redacted": str(redacted),
    }


def run_trufflehog(model_dir: Path) -> dict[str, Any] | None:
    """
    Scan ``model_dir`` for secrets using TruffleHog filesystem mode.

    Returns summary dict for ``tool_results["secrets"]``, or ``None`` if binary missing.
    """
    if not model_dir.is_dir():
        return None

    if not trufflehog_available():
        return {
            "available": False,
            "secret_count": 0,
            "verified_count": 0,
            "by_detector": {},
            "secrets": [],
            "scan_mode": "trufflehog_filesystem",
            "note": "trufflehog binary not found on PATH — secret scan skipped",
        }

    cmd = [
        "trufflehog",
        "filesystem",
        str(model_dir),
        "--json",
        "--no-update",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {
            "available": True,
            "secret_count": 0,
            "verified_count": 0,
            "by_detector": {},
            "secrets": [],
            "scan_mode": "trufflehog_filesystem",
            "error": str(exc)[:500],
        }

    secrets: list[dict[str, Any]] = []
    for line in (proc.stdout or "").splitlines():
        record = _parse_trufflehog_line(line)
        if not record:
            continue
        entry = _extract_secret_entry(record, model_dir)
        file_ref = entry.get("file") or ""
        if file_ref != "unknown":
            candidate = model_dir / file_ref
            if candidate.exists() and _should_skip_path(candidate, model_dir):
                continue
            if any(part in _SKIP_DIR_NAMES for part in Path(file_ref).parts):
                continue
        secrets.append(entry)

    by_detector: dict[str, int] = {}
    verified_count = 0
    for s in secrets:
        det = s.get("detector") or "unknown"
        by_detector[det] = by_detector.get(det, 0) + 1
        if s.get("verified"):
            verified_count += 1

    files_scanned = sum(1 for p in model_dir.rglob("*") if p.is_file() and not _should_skip_path(p, model_dir))

    return {
        "available": True,
        "secret_count": len(secrets),
        "verified_count": verified_count,
        "by_detector": by_detector,
        "secrets": secrets[:100],
        "files_scanned": files_scanned,
        "scan_mode": "trufflehog_filesystem",
        "exit_code": proc.returncode,
    }


def secret_tier(summary: dict[str, Any] | None) -> str:
    """Map secret scan summary to nutrition-label tier."""
    if not summary or not summary.get("available", True):
        return "low"
    if summary.get("verified_count", 0) > 0:
        return "critical"
    if summary.get("secret_count", 0) > 0:
        return "high"
    return "low"
