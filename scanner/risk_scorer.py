"""
Merge ModelScan, Fickling, and ModelAudit into one nutrition-label grade.

Week 3 rubric:
  - ModelScan: primary tier from pickle/H5/SavedModel issues
  - Fickling: pickle depth; LIKELY_UNSAFE alone stays low when ModelScan clean
  - ModelAudit: scoped to safetensors/onnx only; only actionable issues move tier/score
"""

from __future__ import annotations

import hashlib
from typing import Any

from scanner.format_detector import FileFormatSummary
from scanner.modelaudit_scan import modelaudit_tier
from scanner.pickle_scan import modelscan_tier
from scanner.schemas import Finding, RiskScoreResult, Severity

_TIER_SCORE = {"low": 10, "medium": 40, "high": 70, "critical": 95}
_TIER_RANK = {Severity.low: 0, Severity.medium: 1, Severity.high: 2, Severity.critical: 3}


def _finding_id(source: str, file_path: str | None, title: str) -> str:
    raw = f"{source}:{file_path or ''}:{title}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _severity_enum(tier: str) -> Severity:
    try:
        return Severity(tier.lower())
    except ValueError:
        return Severity.low


def _max_tier(a: Severity, b: Severity) -> Severity:
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


def _findings_from_modelscan_issues(
    issues: list[Any], default_tier: Severity
) -> list[Finding]:
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


def score(
    model_id: str,
    modelscan_payload: dict[str, Any],
    fickling_report: dict[str, Any] | None,
    format_summary: FileFormatSummary | None = None,
    modelaudit_summary: dict[str, Any] | None = None,
) -> RiskScoreResult:
    ms_tier_str = modelscan_tier(modelscan_payload)
    ms_tier = _severity_enum(ms_tier_str)
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    issues = modelscan_payload.get("issues") or []
    findings = _findings_from_modelscan_issues(issues, ms_tier)

    tier = ms_tier
    score_val = _TIER_SCORE[ms_tier.value]

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

    fick_sev = (fickling_report or {}).get("severity")
    if fick_sev and not safetensors_only:
        if fick_sev == "LIKELY_OVERTLY_MALICIOUS":
            tier = _max_tier(tier, Severity.high)
            score_val = max(score_val, 75)
            findings.append(
                Finding(
                    id=_finding_id("fickling", fickling_report.get("file"), "overtly malicious pickle"),
                    source="fickling",
                    title="fickling: likely overtly malicious",
                    severity=Severity.high,
                    file_path=fickling_report.get("file"),
                    description=f"fickling severity {fick_sev}",
                    raw_tool_severity=fick_sev,
                    remediation="do not deploy without manual review",
                )
            )
        elif fick_sev in ("LIKELY_UNSAFE", "POSSIBLY_UNSAFE"):
            if tier == Severity.low and not counts.get("HIGH") and not counts.get("CRITICAL"):
                score_val = max(score_val, 18 if fick_sev == "LIKELY_UNSAFE" else 28)
            findings.append(
                Finding(
                    id=_finding_id("fickling", fickling_report.get("file"), "pickle safety signal"),
                    source="fickling",
                    title="pickle safety signal from fickling",
                    severity=Severity.low if tier == Severity.low else tier,
                    file_path=fickling_report.get("file"),
                    description=(
                        f"fickling {fick_sev} on {fickling_report.get('pytorch_format', 'pickle')}; "
                        f"modelscan issues={modelscan_payload.get('summary', {}).get('total_issues', 0)}"
                    ),
                    raw_tool_severity=fick_sev,
                    remediation="review; may be benign pytorch stacked pickle",
                )
            )

    # ModelAudit — only pre-filtered actionable issues (safetensors/onnx)
    if modelaudit_summary and modelaudit_summary.get("actionable_issue_count", 0) > 0:
        ma_tier_str = modelaudit_tier(modelaudit_summary)
        ma_tier = _severity_enum(ma_tier_str)
        tier = _max_tier(tier, ma_tier)
        score_val = max(score_val, _TIER_SCORE.get(ma_tier.value, score_val))
        # cap bump when pickle path already low (avoid false positive inflation)
        if ms_tier == Severity.low and tier == Severity.low:
            score_val = min(score_val, 28)
        findings.extend(_findings_from_modelaudit(modelaudit_summary))

    return RiskScoreResult(
        overall_risk_score=min(100, max(0, score_val)),
        severity_tier=tier,
        findings=findings,
    )
