"""
Merge ModelScan, Fickling, and ModelAudit into one nutrition-label grade.

This is the policy layer between raw tool JSON and ``ScanResult`` / Postgres ``findings``.
See calibration table in ``scanner/README.md`` (gpt2 → low/18, extension-mismatch PoC → critical/95).

Precedence (tier is **max** across tools, not additive):
  - ModelScan: extension-routed pickle/H5/SavedModel; primary when it fires
  - Fickling: pickle AST on every pickle-family file; LIKELY_UNSAFE alone stays **low**
    when ModelScan is clean (benign PyTorch stacked pickles)
  - ModelAudit: content-routed on candidate files; actionable issues raise tier

Defense-in-depth: the same threat may appear in multiple tools. Dedupe findings
by ``(normalized_file_path, signal)`` and record ``corroborated_by`` — agreement
increases reviewer confidence; it does not add to the numeric score.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from scanner.format_detector import FileFormatSummary
from scanner.modelaudit_scan import modelaudit_tier, normalize_issue_path
from scanner.pickle_scan import modelscan_tier
from scanner.schemas import Finding, RiskScoreResult, Severity

# Default score anchors per tier (overridden by explicit CRITICAL/HIGH counts).
_TIER_SCORE = {"low": 10, "medium": 40, "high": 70, "critical": 95}
_TIER_RANK = {Severity.low: 0, Severity.medium: 1, Severity.high: 2, Severity.critical: 3}


def _finding_id(source: str, file_path: str | None, title: str) -> str:
    """Stable 16-char hex id for UI/DB (not a UUID — deterministic from content)."""
    raw = f"{source}:{file_path or ''}:{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _severity_enum(tier: str) -> Severity:
    """Parse tier string; unknown values downgrade to low."""
    try:
        return Severity(tier.lower())
    except ValueError:
        return Severity.low


def _max_tier(a: Severity, b: Severity) -> Severity:
    """Return the more severe of two tier enums."""
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


def _max_severity(a: Severity, b: Severity) -> Severity:
    """Alias for finding merge — same as ``_max_tier``."""
    return _max_tier(a, b)


def _normalize_path_for_dedupe(file_path: str | None) -> str:
    """
    Normalize paths so ModelAudit absolute paths match Fickling relative paths.

    Falls back to basename when prefixes differ between tools.
    """
    if not file_path:
        return ""
    p = normalize_issue_path(file_path)
    return Path(p).name if p else ""


def _signal_from_finding(f: Finding) -> str:
    """
    Extract a dedupe key fragment from description/title/raw_tool_severity.

    Aligns Fickling "dangerous global" messages with ModelAudit import_reference fields.
    """
    desc = (f.description or "").lower()
    for pat in (
        r"dangerous global:\s*([\w.]+)",
        r"import_reference['\"]?\s*:\s*['\"]?([\w.]+)",
        r"nt\.system|os\.system",
    ):
        m = re.search(pat, desc)
        if m:
            return m.group(1).lower() if m.lastindex else m.group(0).lower()
    if f.raw_tool_severity:
        return f.raw_tool_severity.lower()
    return (f.title or "")[:80].lower()


def _dedupe_key(f: Finding) -> tuple[str, str]:
    """Bucket key: normalized file + semantic signal."""
    return (_normalize_path_for_dedupe(f.file_path), _signal_from_finding(f))


def _merge_findings(findings: list[Finding]) -> list[Finding]:
    """
    Collapse duplicate (file, signal) rows from different tools.

    Keeps highest severity; primary ``source`` stays; other tools → ``corroborated_by``.
    Preserves the longer description when merging.
    """
    buckets: dict[tuple[str, str], Finding] = {}
    order: list[tuple[str, str]] = []

    for f in findings:
        key = _dedupe_key(f)
        if key not in buckets:
            buckets[key] = f
            order.append(key)
            continue
        existing = buckets[key]
        merged_sev = _max_severity(existing.severity, f.severity)
        corro = list(existing.corroborated_by or [])
        if f.source != existing.source and f.source not in corro:
            corro.append(f.source)
        if existing.source != f.source and existing.source not in corro:
            corro.append(existing.source)
        buckets[key] = existing.model_copy(
            update={
                "severity": merged_sev,
                "corroborated_by": corro or None,
                "description": existing.description
                if len(existing.description) >= len(f.description)
                else f.description,
            }
        )

    return [buckets[k] for k in order]


def _findings_from_modelscan_issues(
    issues: list[Any], default_tier: Severity
) -> list[Finding]:
    """Map ModelScan ``issues[]`` entries into normalized ``Finding`` rows."""
    out: list[Finding] = []
    for i, issue in enumerate(issues):
        if not isinstance(issue, dict):
            continue
        sev_raw = (issue.get("severity") or issue.get("level") or "LOW").upper()
        sev_map = {
            "CRITICAL": Severity.critical,
            "HIGH": Severity.high,
            "MEDIUM": Severity.medium,
            "LOW": Severity.low,
        }
        sev = sev_map.get(sev_raw, default_tier)
        file_path = issue.get("file") or issue.get("path")
        title = issue.get("title") or issue.get("description") or f"modelscan issue {i}"
        desc = issue.get("description") or str(issue)
        out.append(
            Finding(
                id=_finding_id("modelscan", file_path, title),
                source="modelscan",
                title=str(title)[:200],
                severity=sev,
                file_path=file_path,
                description=str(desc)[:2000],
                raw_tool_severity=sev_raw,
            )
        )
    return out


def _findings_from_modelaudit(summary: dict[str, Any]) -> list[Finding]:
    """Map actionable ModelAudit issues (already noise-filtered) to ``Finding`` rows."""
    out: list[Finding] = []
    for i, issue in enumerate(summary.get("issues") or []):
        if not isinstance(issue, dict):
            continue
        sev_raw = (issue.get("severity") or "medium").lower()
        sev_map = {
            "critical": Severity.critical,
            "high": Severity.high,
            "medium": Severity.medium,
            "low": Severity.low,
            "warning": Severity.medium,
            "info": Severity.low,
        }
        sev = sev_map.get(sev_raw, Severity.medium)
        loc = issue.get("location") or issue.get("file")
        title = (issue.get("message") or f"modelaudit issue {i}")[:200]
        out.append(
            Finding(
                id=_finding_id("modelaudit", loc, title),
                source="modelaudit",
                title=title,
                severity=sev,
                file_path=loc,
                description=(issue.get("why") or issue.get("message") or str(issue))[:2000],
                raw_tool_severity=sev_raw,
                remediation="review before deploy",
            )
        )
    return out


def _findings_from_fickling(fickling_report: dict[str, Any]) -> list[Finding]:
    """
    One finding per analyzed file at worst; uses ``per_file`` when present.

    LIKELY_UNSAFE → low severity finding (benign PyTorch calibration).
    LIKELY_OVERTLY_MALICIOUS → high severity finding.
    """
    out: list[Finding] = []
    per_file = fickling_report.get("per_file") or [fickling_report]

    for entry in per_file:
        if not isinstance(entry, dict):
            continue
        fick_sev = entry.get("severity")
        if not fick_sev or fick_sev == "LIKELY_SAFE":
            continue
        file_path = entry.get("file")
        if fick_sev == "LIKELY_OVERTLY_MALICIOUS":
            out.append(
                Finding(
                    id=_finding_id("fickling", file_path, "overtly malicious pickle"),
                    source="fickling",
                    title="fickling: likely overtly malicious",
                    severity=Severity.high,
                    file_path=file_path,
                    description=f"fickling severity {fick_sev}",
                    raw_tool_severity=fick_sev,
                    remediation="do not deploy without manual review",
                )
            )
        elif fick_sev in ("LIKELY_UNSAFE", "POSSIBLY_UNSAFE"):
            out.append(
                Finding(
                    id=_finding_id("fickling", file_path, "pickle safety signal"),
                    source="fickling",
                    title="pickle safety signal from fickling",
                    severity=Severity.low,
                    file_path=file_path,
                    description=(
                        f"fickling {fick_sev} on {entry.get('pytorch_format', 'pickle')}"
                    ),
                    raw_tool_severity=fick_sev,
                    remediation="review; may be benign pytorch stacked pickle",
                )
            )
    return out


def score(
    model_id: str,
    modelscan_payload: dict[str, Any],
    fickling_report: dict[str, Any] | None,
    format_summary: FileFormatSummary | None = None,
    modelaudit_summary: dict[str, Any] | None = None,
) -> RiskScoreResult:
    """
    Compute ``overall_risk_score``, ``severity_tier``, and deduped ``findings``.

    Args:
        model_id: HF repo id (reserved for future per-model policy hooks).
        modelscan_payload: Raw ModelScan output dict.
        fickling_report: Aggregate Fickling report or None if no pickle files.
        format_summary: From ``format_detector`` — ``safetensors_only`` skips Fickling tier bumps.
        modelaudit_summary: Filtered ModelAudit summary from ``run_modelaudit_scoped``.

    Returns:
        ``RiskScoreResult`` consumed by ``schemas.build_scan_result``.
    """
    ms_tier_str = modelscan_tier(modelscan_payload)
    ms_tier = _severity_enum(ms_tier_str)
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    issues = modelscan_payload.get("issues") or []
    findings: list[Finding] = _findings_from_modelscan_issues(issues, ms_tier)

    tier = ms_tier
    score_val = _TIER_SCORE[ms_tier.value]

    # ModelScan severity counts can raise tier/score even when issues[] is sparse.
    if counts.get("CRITICAL", 0):
        tier = Severity.critical
        score_val = 95
    elif counts.get("HIGH", 0):
        tier = Severity.high
        score_val = max(score_val, 70)
    elif counts.get("MEDIUM", 0):
        tier = Severity.medium
        score_val = max(score_val, 45)

    safetensors_only = False
    if format_summary:
        safetensors_only = format_summary.flags.get("safetensors_only", False)

    if fickling_report and not safetensors_only:
        for ff in _findings_from_fickling(fickling_report):
            findings.append(ff)
        fick_sev = fickling_report.get("severity")
        if fick_sev == "LIKELY_OVERTLY_MALICIOUS":
            tier = _max_tier(tier, Severity.high)
            score_val = max(score_val, 75)
        elif fick_sev in ("LIKELY_UNSAFE", "POSSIBLY_UNSAFE"):
            # Benign PyTorch calibration: tier stays low if ModelScan is clean.
            if tier == Severity.low and not counts.get("HIGH") and not counts.get("CRITICAL"):
                score_val = max(score_val, 18 if fick_sev == "LIKELY_UNSAFE" else 28)

    if modelaudit_summary and modelaudit_summary.get("actionable_issue_count", 0) > 0:
        ma_tier_str = modelaudit_tier(modelaudit_summary)
        ma_tier = _severity_enum(ma_tier_str)
        tier = _max_tier(tier, ma_tier)
        score_val = max(score_val, _TIER_SCORE.get(ma_tier.value, score_val))
        findings.extend(_findings_from_modelaudit(modelaudit_summary))

    # After ModelAudit, clamp Fickling finding severities to low when label tier is still low.
    if tier == Severity.low and fickling_report:
        for i, f in enumerate(findings):
            if f.source == "fickling" and f.severity != Severity.low:
                if fickling_report.get("severity") in ("LIKELY_UNSAFE", "POSSIBLY_UNSAFE"):
                    findings[i] = f.model_copy(update={"severity": Severity.low})

    if (
        ms_tier == Severity.low
        and tier == Severity.low
        and (not modelaudit_summary or modelaudit_summary.get("actionable_issue_count", 0) == 0)
    ):
        score_val = min(score_val, 28)

    findings = _merge_findings(findings)

    return RiskScoreResult(
        overall_risk_score=min(100, max(0, score_val)),
        severity_tier=tier,
        findings=findings,
    )
