"""
pydantic data shapes for Track A scanning (security pillar).

week 2 spike — will move to scanner/schemas.py when we extract production package.
aligned with docs/track-a-framework.md and ITSO requirement to reconcile tool disagreement.

reconciliation note (gpt2 lesson):
  fickling may say LIKELY_UNSAFE while modelscan says 0 issues on a known-safe model.
  Finding.raw_tool_severity keeps the tool's native label; Finding.severity is our merged tier.
  week 3 risk scorer decides final weight — schema just carries both signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """normalized severity for dashboard + nutrition label."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Finding(BaseModel):
    """one actionable issue from any scanner tool."""

    id: str  # stable id — uuid or hash of source+file+title
    source: str  # modelscan | fickling | pip_audit | osv | trufflehog | bandit
    title: str
    severity: Severity
    file_path: str | None = None
    description: str
    raw_tool_severity: str | None = None  # e.g. LIKELY_UNSAFE before we reconcile
    remediation: str | None = None


class ScanRequest(BaseModel):
    """input to start a scan job — maps to POST /scans later."""

    model_id: str  # huggingface repo id e.g. gpt2 or facebook/opt-125m
    scan_types: list[str] = Field(default_factory=lambda: ["artifact"])
    # ITSO week 2+ fields — placeholder until data-model.md is committed
    deployment_context: dict[str, Any] | None = None


class ScanResult(BaseModel):
    """structured output after a scan completes — maps to GET /scans/{id}."""

    model_id: str
    status: str  # queued | running | complete | failed
    overall_risk_score: int = 0  # 0-100 rubric — placeholder 0 ok for spike
    severity_tier: Severity
    findings: list[Finding] = Field(default_factory=list)
    scanned_files: list[str] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    scan_metadata: dict[str, Any] = Field(default_factory=dict)

    # spike-only fields from combined_scan.json — drop or fold into findings in production
    fickling_severity: str | None = None


def severity_from_modelscan_tier(tier: str) -> Severity:
    # bridge existing scan_helpers tier strings to enum
    return Severity(tier.lower())


def build_scan_result_from_combined(combined: dict[str, Any]) -> ScanResult:
    """
    convert spike combined_scan.json dict into validated ScanResult.
    used by schemas_demo.py and as reference for week 3 pipeline output.
    """
    tier = combined.get("severity_tier", "low")
    findings: list[Finding] = []

    # if we had structured findings in json, pass them through
    for raw in combined.get("findings", []):
        if isinstance(raw, dict):
            findings.append(Finding(**raw))

    # represent fickling disagreement as a finding stub when severity is elevated but findings empty
    fick_sev = combined.get("fickling_severity")
    tool = combined.get("tool_results", {}).get("fickling", {})
    ms = combined.get("tool_results", {}).get("modelscan", {})
    if fick_sev and fick_sev != "LIKELY_SAFE" and not findings:
        findings.append(
            Finding(
                id=f"fickling-{combined.get('model_id', 'unknown')}-pickle",
                source="fickling",
                title="pickle safety signal from fickling",
                severity=Severity.low if tier == "low" else Severity(tier),
                file_path=tool.get("file"),
                description=(
                    f"fickling reported {fick_sev} on {tool.get('pytorch_format', 'unknown')} "
                    f"(modelscan total_issues={ms.get('total_issues', 0)})"
                ),
                raw_tool_severity=fick_sev,
                remediation="review with modelscan results; may be benign pytorch stacked pickle",
            )
        )

    return ScanResult(
        model_id=combined["model_id"],
        status="complete",
        overall_risk_score=combined.get("overall_risk_score", 0),
        severity_tier=severity_from_modelscan_tier(tier),
        findings=findings,
        scanned_files=combined.get("scanned_files", []),
        tool_results=combined.get("tool_results", {}),
        scan_metadata=combined.get(
            "scan_metadata",
            {"converted_at": datetime.now(timezone.utc).isoformat()},
        ),
        fickling_severity=fick_sev,
    )
