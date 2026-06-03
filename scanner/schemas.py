"""
Pydantic contracts for HF scan output — aligned with ``docs/data-model.md``.

These types are the bridge between tool JSON blobs and future Postgres rows:
``ScanResult`` ≈ one ``scans`` row; each ``Finding`` ≈ one ``findings`` row.

The API/UI should read normalized ``findings`` and ``severity_tier``; investigators
can drill into ``tool_results`` for raw ModelScan/Fickling/ModelAudit payloads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Nutrition-label severity band (maps to ``scans.severity_tier``)."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Finding(BaseModel):
    """
    One actionable issue for reviewers (maps to ``findings`` table).

    ``source`` is the tool that produced the primary row; ``corroborated_by``
    lists other tools that reported the same file/signal (defense-in-depth merge).
    """

    id: str
    source: str
    title: str
    severity: Severity
    file_path: str | None = None
    description: str
    raw_tool_severity: str | None = None
    remediation: str | None = None
    corroborated_by: list[str] | None = None


class ScanRequest(BaseModel):
    """Future API/Celery job payload shape (not wired in CLI yet)."""

    model_id: str
    scan_types: list[str] = Field(default_factory=lambda: ["artifact"])
    deployment_context: dict[str, Any] | None = None


class RiskScoreResult(BaseModel):
    """Output of ``risk_scorer.score`` before wrapping in ``ScanResult``."""

    overall_risk_score: int
    severity_tier: Severity
    findings: list[Finding] = Field(default_factory=list)


class ScanResult(BaseModel):
    """
    Primary artifact written to ``output/<slug>/scan_result.json``.

    ``status`` will support queued/running when Celery workers land (week 5).
    ``fickling_severity`` is kept at top level for quick UI badges on benign pickles.
    """

    model_id: str
    status: str
    overall_risk_score: int = 0
    severity_tier: Severity
    findings: list[Finding] = Field(default_factory=list)
    scanned_files: list[str] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    scan_metadata: dict[str, Any] = Field(default_factory=dict)
    fickling_severity: str | None = None


def severity_from_tier(tier: str | Severity) -> Severity:
    """Coerce string tier from legacy JSON into ``Severity`` enum."""
    if isinstance(tier, Severity):
        return tier
    return Severity(tier.lower())


def build_scan_result(
    model_id: str,
    risk: RiskScoreResult,
    scanned_files: list[str],
    tool_results: dict[str, Any],
    scan_metadata: dict[str, Any],
    fickling_severity: str | None = None,
) -> ScanResult:
    """Assemble final ``ScanResult`` after ``risk_scorer`` and tool runs."""
    return ScanResult(
        model_id=model_id,
        status="complete",
        overall_risk_score=risk.overall_risk_score,
        severity_tier=risk.severity_tier,
        findings=risk.findings,
        scanned_files=scanned_files,
        tool_results=tool_results,
        scan_metadata=scan_metadata,
        fickling_severity=fickling_severity,
    )


def build_scan_result_from_combined(combined: dict[str, Any]) -> ScanResult:
    """
    Upgrade legacy ``combined_scan.json`` (week 2 spike) into ``ScanResult``.

    Prefer ``pipeline.scan_model`` + ``build_scan_result`` for new runs.
    Synthesizes a Fickling finding when only ``fickling_severity`` was present.
    """
    tier = combined.get("severity_tier", "low")
    findings: list[Finding] = []
    for raw in combined.get("findings", []):
        if isinstance(raw, dict):
            findings.append(Finding(**raw))

    fick_sev = combined.get("fickling_severity")
    tool = combined.get("tool_results", {}).get("fickling", {})
    ms = combined.get("tool_results", {}).get("modelscan", {})
    if fick_sev and fick_sev != "LIKELY_SAFE" and not findings:
        findings.append(
            Finding(
                id=f"fickling-{combined.get('model_id', 'unknown')}-pickle",
                source="fickling",
                title="pickle safety signal from fickling",
                severity=Severity.low if tier == "low" else severity_from_tier(tier),
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
        severity_tier=severity_from_tier(tier),
        findings=findings,
        scanned_files=combined.get("scanned_files", []),
        tool_results=combined.get("tool_results", {}),
        scan_metadata=combined.get(
            "scan_metadata",
            {"converted_at": datetime.now(timezone.utc).isoformat()},
        ),
        fickling_severity=fick_sev,
    )
