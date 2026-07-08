"""Per-pillar staleness rules for list-page 'up to date / needs rerun' indicators.

Tweak the constants below when probe sets, scanner tooling, or eval suites change.
"""

from __future__ import annotations

from datetime import date, datetime

# Runs completed before this date predate the current tooling/spec baseline.
CURRENT_SPEC_CUTOFF = date(2026, 7, 1)

# Garak subset: expect roughly this many distinct probe_ids in findings.
SAFETY_EXPECTED_GARAK_PROBES = 26


def _parse_ts(value: str | None) -> datetime | None:
    if not value or value in ("—", ""):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _before_cutoff(ts: str | None) -> bool:
    dt = _parse_ts(ts)
    if dt is None:
        return False
    return dt.date() < CURRENT_SPEC_CUTOFF


def _result(stale: bool, reasons: list[str]) -> dict:
    return {
        "stale": stale,
        "level": "stale" if stale else "current",
        "reasons": reasons,
        "label": "Needs rerun" if stale else "Up to date",
    }


def garak_probe_count_from_data(data: dict) -> int:
    """Count distinct garak_subset_v1 probe_ids in a MergedSafetyResult-shaped dict."""
    findings = data.get("findings") or []
    ids = {
        f.get("probe_id")
        for f in findings
        if isinstance(f, dict)
        and (f.get("probe_suite") or "") == "garak_subset_v1"
        and f.get("probe_id")
        and f.get("probe_id") != "—"
    }
    return len(ids)


def _safety_staleness(row: dict) -> dict:
    reasons: list[str] = []
    if _before_cutoff(row.get("completed_at")):
        reasons.append(f"completed before {CURRENT_SPEC_CUTOFF.isoformat()}")
    if row.get("missing_suites"):
        reasons.append(f"missing suites: {', '.join(row['missing_suites'])}")
    garak_count = row.get("garak_probe_count")
    if garak_count is not None and garak_count < SAFETY_EXPECTED_GARAK_PROBES:
        reasons.append(
            f"garak probe count {garak_count} < expected {SAFETY_EXPECTED_GARAK_PROBES}"
        )
    if (row.get("status") or "").lower() not in ("complete", "completed", ""):
        reasons.append(f"status is {row.get('status')}")
    return _result(bool(reasons), reasons)


def _scan_staleness(row: dict) -> dict:
    reasons: list[str] = []
    if row.get("scanned_file_count", 0) == 0:
        reasons.append("0 files scanned")
    if _before_cutoff(row.get("scanned_at")):
        reasons.append(f"scanned before {CURRENT_SPEC_CUTOFF.isoformat()}")
    if (row.get("status") or "").lower() not in ("complete", "completed", "unknown", ""):
        reasons.append(f"status is {row.get('status')}")
    return _result(bool(reasons), reasons)


def _eval_staleness(row: dict) -> dict:
    from frontend.eval_launch import SUITES

    reasons: list[str] = []
    suite = row.get("suite") or row.get("suite_version") or ""
    if _before_cutoff(row.get("timestamp")):
        reasons.append(f"completed before {CURRENT_SPEC_CUTOFF.isoformat()}")
    if suite and suite not in SUITES and not suite.startswith("custom_"):
        reasons.append(f"suite {suite!r} is not a current curated suite")
    return _result(bool(reasons), reasons)


def _benchmark_staleness(row: dict) -> dict:
    from frontend.benchmark_data import is_reference_slug

    slug = row.get("slug") or ""
    if is_reference_slug(slug):
        return _result(False, [])
    reasons: list[str] = []
    ts = row.get("timestamp_raw") or row.get("timestamp")
    if _before_cutoff(ts):
        reasons.append(f"completed before {CURRENT_SPEC_CUTOFF.isoformat()}")
    return _result(bool(reasons), reasons)


_PILLAR_FN = {
    "safety": _safety_staleness,
    "scan": _scan_staleness,
    "eval": _eval_staleness,
    "benchmark": _benchmark_staleness,
}


def staleness_for(pillar: str, row: dict) -> dict:
    """Return staleness dict for one list-row."""
    fn = _PILLAR_FN.get(pillar)
    if fn is None:
        return _result(False, [])
    return fn(row)


def attach_staleness(rows: list[dict], pillar: str) -> None:
    """Mutate each row in place with a ``staleness`` dict."""
    for row in rows:
        row["staleness"] = staleness_for(pillar, row)
