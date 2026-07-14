"""Per-pillar staleness rules for list-page 'up to date / needs rerun' indicators.

Rules are pillar-specific and derived from current tooling on disk (scanner
version, garak probe_spec, eval suite files, benchmark scripts) — not a global
calendar cutoff. See ``dbutils.staleness_spec``.
"""

from __future__ import annotations

from dbutils import staleness_spec


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


def _result(stale: bool, reasons: list[str]) -> dict:
    return {
        "stale": stale,
        "level": "stale" if stale else "current",
        "reasons": reasons,
        "label": "Needs rerun" if stale else "Up to date",
    }


def _safety_staleness(row: dict) -> dict:
    reasons = staleness_spec.safety_staleness_reasons(row)
    return _result(bool(reasons), reasons)


def _scan_staleness(row: dict) -> dict:
    reasons = staleness_spec.scan_staleness_reasons(row)
    return _result(bool(reasons), reasons)


def _eval_staleness(row: dict) -> dict:
    reasons = staleness_spec.eval_staleness_reasons(row)
    return _result(bool(reasons), reasons)


def _benchmark_staleness(row: dict) -> dict:
    reasons = staleness_spec.benchmark_staleness_reasons(row)
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
