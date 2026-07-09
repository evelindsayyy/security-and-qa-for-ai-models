"""Read/write run_meta.json sidecars for auth + fingerprint metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_run_meta(path: Path) -> dict[str, Any]:
    """Load run_meta.json from a directory or return empty dict."""
    from dbutils import fs_safe

    if fs_safe.is_file(path) and path.name == "run_meta.json":
        meta_path = path
    else:
        meta_path = path / "run_meta.json"
    if not fs_safe.is_file(meta_path):
        return {}
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_run_meta(
    directory: Path,
    *,
    visibility: str,
    config_fingerprint: str,
    config_json: dict[str, Any],
    owner_user_id: str | None = None,
    owner_netid: str | None = None,
    reused_from: str | None = None,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "visibility": visibility,
        "config_fingerprint": config_fingerprint,
        "config_json": config_json,
        "owner_user_id": owner_user_id,
        "owner_netid": owner_netid,
    }
    if reused_from:
        payload["reused_from"] = reused_from
    (directory / "run_meta.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def merge_into_scan_meta(scan_dir: Path, run_meta: dict[str, Any]) -> None:
    """Merge auth fields into existing scan_meta.json if present."""
    meta_path = scan_dir / "scan_meta.json"
    base: dict[str, Any] = {}
    from dbutils import fs_safe

    if fs_safe.is_file(meta_path):
        try:
            base = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            base = {}
    base.update(run_meta)
    meta_path.write_text(json.dumps(base, indent=2), encoding="utf-8")


def read_run_meta_for_pillar(directory: Path, *, pillar: str) -> dict[str, Any]:
    """Auth/visibility sidecar for *directory*, pillar-aware.

    Every pillar except ``scan`` writes ``run_meta.json`` straight into the
    artifact directory (``write_run_meta``), so ``read_run_meta`` alone is
    enough. Scan writes its auth fields into ``scan_meta.json`` instead
    (``merge_into_scan_meta``) since that sidecar already existed — merge it
    in here so every pillar's file-fallback read path (visibility filtering,
    ingest) sees the same auth fields regardless of which file they live in.
    """
    meta = read_run_meta(directory)
    if pillar == "scan":
        from dbutils import fs_safe

        scan_meta_path = directory / "scan_meta.json"
        if fs_safe.is_file(scan_meta_path):
            try:
                scan_meta = json.loads(scan_meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                scan_meta = {}
            if isinstance(scan_meta, dict):
                for key in ("visibility", "config_fingerprint", "config_json", "owner_user_id", "owner_netid"):
                    if key in scan_meta and key not in meta:
                        meta[key] = scan_meta[key]
    return meta
