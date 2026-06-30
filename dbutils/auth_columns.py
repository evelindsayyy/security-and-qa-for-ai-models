"""Merge auth / fingerprint metadata from run sidecars into loader rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dbutils.run_meta import read_run_meta


def auth_fields_from_artifact(artifact_path: Path, *, pillar: str) -> dict[str, Any]:
    """Read run_meta.json or merged scan_meta for ingest columns."""
    if pillar == "scan":
        directory = artifact_path.parent
        meta = read_run_meta(directory)
        scan_meta_path = directory / "scan_meta.json"
        if scan_meta_path.is_file():
            import json

            try:
                scan_meta = json.loads(scan_meta_path.read_text(encoding="utf-8"))
                if isinstance(scan_meta, dict):
                    for key in (
                        "visibility",
                        "config_fingerprint",
                        "config_json",
                        "owner_user_id",
                    ):
                        if key in scan_meta and key not in meta:
                            meta[key] = scan_meta[key]
            except (OSError, json.JSONDecodeError):
                pass
    elif pillar in ("eval", "benchmark"):
        meta = read_run_meta(artifact_path.parent / artifact_path.stem)
    else:
        meta = read_run_meta(artifact_path.parent)

    visibility = meta.get("visibility") or "public"
    owner = meta.get("owner_user_id")
    fp = meta.get("config_fingerprint")
    cfg = meta.get("config_json") or {}

    return {
        "visibility": visibility,
        "owner_user_id": owner,
        "config_fingerprint": fp,
        "config_json": cfg if isinstance(cfg, dict) else {},
    }


def apply_auth_defaults(row: dict[str, Any], fields: dict[str, Any]) -> None:
    row.setdefault("visibility", fields.get("visibility") or "public")
    row.setdefault("owner_user_id", fields.get("owner_user_id"))
    row.setdefault("config_fingerprint", fields.get("config_fingerprint"))
    row.setdefault("config_json", fields.get("config_json") or {})
