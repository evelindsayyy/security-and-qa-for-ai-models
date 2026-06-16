"""
Postgres-backed data source for /scans — same dict contracts as scan_data.py,
used only when POSTGRES_DSN is set and reachable.

Freshness model: the database holds whatever the loader last synced; brand-new
scans exist only as files until the next ``load_scans.py --apply``. So
``get_scans_data_db()`` MERGES: DB rows are preferred per slug (latest
``completed_at`` per hf_repo), and any scan_result.json on disk not yet in the
DB is summarized from the file. Findings for list-table columns (count +
severity breakdown) are batch-loaded from ``public.findings``. Detail falls
back to disk when the slug is missing from Postgres.

Severable by design: delete this module and the dispatcher in scan_data.py
reverts to pure file reads.
"""

from __future__ import annotations

import time

from dbutils import load_repo_env, resolve_dsn

from frontend.path_safety import is_safe_slug
from frontend.scan_data import (
    OUTPUT_DIR,
    _build_scan_detail,
    _summarize_from_data,
)
from scanner.paths import safe_dir_name, slug_to_model_id

load_repo_env()

_DSN_KEYS = ("POSTGRES_DSN", "DATABASE_URL")
_CONNECT_TIMEOUT_S = 2
_AVAILABILITY_TTL_S = 60.0
_avail_cache = {"checked_at": 0.0, "ok": False}


def _dsn() -> str | None:
    return resolve_dsn(*_DSN_KEYS)


def available() -> bool:
    """True when a DSN is configured, psycopg is installed, and Postgres answers."""
    dsn = _dsn()
    if not dsn:
        return False
    now = time.monotonic()
    if now - _avail_cache["checked_at"] < _AVAILABILITY_TTL_S:
        return _avail_cache["ok"]
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=_CONNECT_TIMEOUT_S):
            ok = True
    except Exception:
        ok = False
    _avail_cache.update(checked_at=now, ok=ok)
    return ok


def _connect():
    import psycopg

    return psycopg.connect(_dsn(), connect_timeout=_CONNECT_TIMEOUT_S)


_LATEST_SCANS_SQL = """
SELECT DISTINCT ON (hf_repo)
    id::text, hf_repo, status, overall_risk_score, severity_tier,
    scanned_files, tool_results, scan_metadata, started_at, completed_at
FROM public.scans
ORDER BY hf_repo, completed_at DESC NULLS LAST
"""

_DETAIL_SCAN_SQL = """
SELECT id::text, hf_repo, status, overall_risk_score, severity_tier,
       scanned_files, tool_results, scan_metadata, started_at, completed_at
FROM public.scans
WHERE hf_repo = %(hf_repo)s
ORDER BY completed_at DESC NULLS LAST
LIMIT 1
"""

_FINDINGS_SQL = """
SELECT finding_key, source, title, severity, file_path, description,
       raw_tool_severity, remediation, corroborated_by
FROM public.findings
WHERE scan_id = %(scan_id)s::uuid
ORDER BY severity, source, title
"""

_FINDINGS_FOR_SCANS_SQL = """
SELECT scan_id::text, finding_key, source, title, severity, file_path, description,
       raw_tool_severity, remediation, corroborated_by
FROM public.findings
WHERE scan_id = ANY(%(scan_ids)s::uuid[])
ORDER BY scan_id, severity, source, title
"""


def _slug_for_scan(hf_repo: str, scan_metadata: dict | None) -> str:
    meta = scan_metadata or {}
    return meta.get("output_slug") or safe_dir_name(hf_repo)


def _findings_to_json(rows: list[tuple]) -> list[dict]:
    out: list[dict] = []
    for (
        finding_key,
        source,
        title,
        severity,
        file_path,
        description,
        raw_tool_severity,
        remediation,
        corroborated_by,
    ) in rows:
        out.append(
            {
                "id": finding_key,
                "source": source,
                "title": title,
                "severity": (severity or "unknown").lower(),
                "file_path": file_path,
                "description": description or "",
                "raw_tool_severity": raw_tool_severity,
                "remediation": remediation,
                "corroborated_by": corroborated_by or [],
            }
        )
    return out


def _scan_tuple_to_data(
    scan_row: tuple,
    findings_json: list[dict],
) -> dict:
    """Rebuild ScanResult-shaped dict from DB columns."""
    (
        _scan_id,
        hf_repo,
        status,
        overall_risk_score,
        severity_tier,
        scanned_files,
        tool_results,
        scan_metadata,
        _started_at,
        _completed_at,
    ) = scan_row
    meta = dict(scan_metadata or {})
    fickling_severity = meta.get("fickling_severity")
    if not fickling_severity:
        fick = (tool_results or {}).get("fickling") or {}
        fickling_severity = fick.get("severity")

    return {
        "model_id": hf_repo,
        "status": status or "unknown",
        "overall_risk_score": overall_risk_score or 0,
        "severity_tier": (severity_tier or "unknown").lower(),
        "findings": findings_json,
        "scanned_files": scanned_files or [],
        "tool_results": tool_results or {},
        "scan_metadata": meta,
        "fickling_severity": fickling_severity,
    }


def _fetch_findings_by_scan_id(conn, scan_ids: list[str]) -> dict[str, list[dict]]:
    """Batch-load findings for list-table rows (one query for all scan ids)."""
    if not scan_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(_FINDINGS_FOR_SCANS_SQL, {"scan_ids": scan_ids})
        rows = cur.fetchall()
    grouped: dict[str, list[dict]] = {scan_id: [] for scan_id in scan_ids}
    for scan_id, *finding in rows:
        grouped.setdefault(scan_id, []).extend(_findings_to_json([finding]))
    return grouped


def _summarize_db_scan(scan_row: tuple, findings_json: list[dict] | None = None) -> dict | None:
    """Comparison-table row from one scans tuple (same keys as _summarize_from_data)."""
    meta = scan_row[7] or {}
    slug = _slug_for_scan(scan_row[1], meta)
    data = _scan_tuple_to_data(scan_row, findings_json or [])
    return _summarize_from_data(data, slug)


def _hf_repo_candidates(slug: str) -> list[str]:
    """Map UI slug to possible hf_repo values stored in scans."""
    candidates = [slug_to_model_id(slug)]
    if slug not in candidates:
        candidates.append(slug)
    return candidates


def get_scans_data_db() -> dict:
    """DB-preferred merge of every known scan (DB rows + not-yet-loaded files)."""
    from frontend.scan_data import _summarize_scan

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_LATEST_SCANS_SQL)
            scan_rows = cur.fetchall()
        findings_by_scan = _fetch_findings_by_scan_id(conn, [row[0] for row in scan_rows])
        db_rows = [
            _summarize_db_scan(row, findings_by_scan.get(row[0], []))
            for row in scan_rows
        ]
    db_rows = [r for r in db_rows if r is not None]

    seen_slugs = {r["slug"] for r in db_rows}
    file_rows: list[dict] = []
    if OUTPUT_DIR.exists():
        for path in sorted(OUTPUT_DIR.glob("*/scan_result.json")):
            slug = path.parent.name
            if slug in seen_slugs:
                continue
            row = _summarize_scan(path, slug)
            if row is not None:
                file_rows.append(row)

    rows = db_rows + file_rows
    rows.sort(key=lambda r: r["overall_risk_score"], reverse=True)
    tiers = sorted({r["severity_tier"] for r in rows})
    tier_summary = ", ".join(tiers) if tiers else ""

    return {
        "has_scans": bool(rows),
        "output_dir": str(OUTPUT_DIR),
        "scans": rows,
        "tier_summary": tier_summary,
    }


def get_scan_detail_db(slug: str) -> dict | None:
    """Detail-page payload from Postgres; None if slug isn't loaded."""
    if not is_safe_slug(slug):
        return None

    with _connect() as conn:
        with conn.cursor() as cur:
            scan_row = None
            for hf_repo in _hf_repo_candidates(slug):
                cur.execute(_DETAIL_SCAN_SQL, {"hf_repo": hf_repo})
                scan_row = cur.fetchone()
                if scan_row is not None:
                    break
            if scan_row is None:
                return None

            cur.execute(_FINDINGS_SQL, {"scan_id": scan_row[0]})
            findings = _findings_to_json(cur.fetchall())

    data = _scan_tuple_to_data(scan_row, findings)
    detail_slug = _slug_for_scan(scan_row[1], data.get("scan_metadata"))
    return _build_scan_detail(detail_slug, data)
