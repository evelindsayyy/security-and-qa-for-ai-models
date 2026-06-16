"""
load_scans.py — scan_result.json -> public.scans / public.findings (scan_schema.sql).

Reads every ``scan_result.json`` under ``scanner/output/<slug>/`` and loads
validated ``ScanResult`` rows into Postgres. Uses shared ``dbutils`` for env,
file IO, connect, JSONB params, and the dry-run CLI contract.

SAFE BY DEFAULT: without ``--apply`` this is a dry run — it prints what WOULD
be loaded and never opens a database connection.

Idempotent: re-running with ``--apply`` cannot duplicate rows — every INSERT
uses ON CONFLICT DO NOTHING on the schema unique keys.

Run from repo root:
    uv run python scanner/db/load_scans.py                 # dry run
    uv run python scanner/db/load_scans.py --apply         # real load (needs psycopg + DSN)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Repo root on sys.path so ``scanner`` and ``dbutils`` import cleanly.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dbutils import apply_loader, iter_files, jsonb_param, load_repo_env, read_json
from dbutils.cli import add_ingest_arguments
from dbutils.ingest import exit_if_apply_without_dsn, print_dry_run_hint
from scanner.paths import safe_dir_name
from scanner.schemas import ScanResult

SCANNER = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SCANNER / "output"


# ---------------------------------------------------------------------------
# Pure transforms: ScanResult dict -> table-row dicts (no DB, unit-testable)
# ---------------------------------------------------------------------------


def _parse_iso_timestamp(value: str | None) -> str | None:
    """Return ISO string suitable for timestamptz bind, or None."""
    if not value or value == "—":
        return None
    try:
        # Accept Z suffix and offset forms from scan_metadata.scanned_at.
        normalized = value.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)
        return value.replace("Z", "+00:00") if value.endswith("Z") else value
    except ValueError:
        return None


def _started_at_from_meta(scan_dir: Path) -> str | None:
    """Optional started_at from UI launch artifact scan_meta.json."""
    meta_path = scan_dir / "scan_meta.json"
    if not meta_path.is_file():
        return None
    meta = read_json(meta_path)
    if not meta:
        return None
    return _parse_iso_timestamp(meta.get("started_at"))


def scan_row(data: dict[str, Any], slug: str, *, scan_dir: Path | None = None) -> dict:
    """One ``scans`` row from a validated ScanResult dict."""
    meta = dict(data.get("scan_metadata") or {})
    # Preserve top-level UI badge inside metadata for DB round-trip reads.
    if data.get("fickling_severity") and "fickling_severity" not in meta:
        meta["fickling_severity"] = data["fickling_severity"]
    meta["output_slug"] = slug

    completed_at = _parse_iso_timestamp(meta.get("scanned_at"))
    started_at = None
    if scan_dir is not None:
        started_at = _started_at_from_meta(scan_dir)

    tier = data.get("severity_tier", "unknown")
    if hasattr(tier, "value"):
        tier = tier.value

    return {
        "model_id": None,
        "hf_repo": data["model_id"],
        "status": data.get("status") or "complete",
        "overall_risk_score": int(data.get("overall_risk_score") or 0),
        "severity_tier": str(tier).lower(),
        "scanned_files": data.get("scanned_files") or [],
        "tool_results": data.get("tool_results") or {},
        "scan_metadata": meta,
        "started_at": started_at,
        "completed_at": completed_at,
    }


def finding_rows(data: dict[str, Any]) -> list[dict]:
    """``findings`` rows for one scan (finding_key wired after scan INSERT)."""
    rows: list[dict] = []
    for raw in data.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        sev = raw.get("severity", "unknown")
        if hasattr(sev, "value"):
            sev = sev.value
        corroborated = raw.get("corroborated_by")
        rows.append(
            {
                "finding_key": raw.get("id") or "",
                "source": (raw.get("source") or "unknown").lower(),
                "title": raw.get("title") or "—",
                "severity": str(sev).lower(),
                "file_path": raw.get("file_path"),
                "description": (raw.get("description") or "").strip(),
                "raw_tool_severity": raw.get("raw_tool_severity"),
                "remediation": raw.get("remediation"),
                "corroborated_by": corroborated,
            }
        )
    return rows


def load_file(path: Path) -> tuple[dict, list[dict]] | None:
    """Parse one ``scan_result.json`` into (scan_row, finding_rows).

    Returns None for empty/unparsable files (same tolerance as the frontend).
    """
    data = read_json(path)
    if data is None:
        return None
    try:
        validated = ScanResult.model_validate(data)
        payload = validated.model_dump(mode="json")
    except Exception:
        return None

    slug = path.parent.name
    scan = scan_row(payload, slug, scan_dir=path.parent)
    if not scan["completed_at"]:
        return None
    findings = finding_rows(payload)
    return scan, findings


# ---------------------------------------------------------------------------
# SQL — idempotent INSERTs keyed to scan_schema.sql UNIQUE constraints
# ---------------------------------------------------------------------------

_SCAN_INSERT = """
INSERT INTO public.scans (
    model_id, hf_repo, status, overall_risk_score, severity_tier,
    scanned_files, tool_results, scan_metadata, started_at, completed_at)
VALUES (
    %(model_id)s, %(hf_repo)s, %(status)s, %(overall_risk_score)s, %(severity_tier)s,
    %(scanned_files)s::jsonb, %(tool_results)s::jsonb, %(scan_metadata)s::jsonb,
    %(started_at)s, %(completed_at)s)
ON CONFLICT (hf_repo, completed_at) DO NOTHING
"""

_SCAN_SELECT = """
SELECT id FROM public.scans
WHERE hf_repo = %(hf_repo)s AND completed_at = %(completed_at)s
"""

_FINDING_INSERT = """
INSERT INTO public.findings (
    scan_id, finding_key, source, title, severity, file_path, description,
    raw_tool_severity, remediation, corroborated_by)
VALUES (
    %(scan_id)s, %(finding_key)s, %(source)s, %(title)s, %(severity)s,
    %(file_path)s, %(description)s, %(raw_tool_severity)s, %(remediation)s,
    %(corroborated_by)s::jsonb)
ON CONFLICT (scan_id, finding_key) DO NOTHING
"""


def _scan_params(scan: dict) -> dict:
    """Bind-ready params with JSONB columns serialized."""
    return {
        **scan,
        "scanned_files": jsonb_param(scan["scanned_files"]),
        "tool_results": jsonb_param(scan["tool_results"]),
        "scan_metadata": jsonb_param(scan["scan_metadata"]),
    }


def load_into(conn, parsed: list[tuple[dict, list[dict]]]) -> None:
    """All cursor work + one commit. ``conn`` is DB-API-shaped (psycopg or fake)."""
    with conn.cursor() as cur:
        for scan, findings in parsed:
            params = _scan_params(scan)
            cur.execute(_SCAN_INSERT, params)
            cur.execute(_SCAN_SELECT, params)
            row = cur.fetchone()
            if not row:
                continue
            scan_id = row[0]

            for finding in findings:
                if not finding["finding_key"]:
                    continue
                fparams = {
                    **finding,
                    "scan_id": scan_id,
                    "corroborated_by": jsonb_param(finding["corroborated_by"])
                    if finding.get("corroborated_by") is not None
                    else None,
                }
                cur.execute(_FINDING_INSERT, fparams)
    conn.commit()


def main() -> int:
    load_repo_env()
    ap = argparse.ArgumentParser(description="Load scan_result.json files into Postgres.")
    ap.add_argument("--output-dir", type=Path, default=OUTPUT_DIR,
                    help="scanner output root (default: scanner/output)")
    add_ingest_arguments(ap, dsn_env_keys=("POSTGRES_DSN", "DATABASE_URL"))
    args = ap.parse_args()

    paths = iter_files(args.output_dir, "*/scan_result.json")
    parsed = [t for t in (load_file(p) for p in paths) if t is not None]

    print(f"{len(parsed)} loadable scan(s) in {args.output_dir}:")
    for scan, findings in parsed:
        meta = scan["scan_metadata"]
        slug = meta.get("output_slug") or safe_dir_name(scan["hf_repo"])
        print(
            f"  {slug}: repo={scan['hf_repo']}  tier={scan['severity_tier']}  "
            f"score={scan['overall_risk_score']}  findings={len(findings)}  "
            f"completed_at={scan['completed_at']}"
        )

    if not args.apply:
        print_dry_run_hint()
        return 0
    exit_if_apply_without_dsn(args.dsn)
    apply_loader(
        args.dsn,
        lambda conn: load_into(conn, parsed),
        item_count=len(parsed),
        item_label="scan(s)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
