"""
Pydantic contracts for gateway safety output — aligned with ``docs/data-model.md``.

``SafetyRunResult`` ≈ one ``safety_runs`` row; each ``SafetyFinding`` ≈ one
``safety_findings`` row. ``MergedSafetyResult`` is the week-3 on-disk aggregate
before Postgres (mirrors ``scanner/schemas.ScanResult`` + ``risk_scorer`` merge).

UI reads normalized ``findings`` and ``summary_pass_rate``; investigators drill
into ``tool_results`` per probe suite.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SafetySeverity(str, Enum):
    """Finding severity band (maps to ``safety_findings.severity``)."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SafetyCategory(str, Enum):
    """``safety_findings.category`` — extend as Duke probes grow."""

    smoke = "smoke"
    policy = "policy"
    jailbreak = "jailbreak"
    leakage = "leakage"
    toxicity = "toxicity"


class SafetySource(str, Enum):
    """``safety_findings.source``"""

    garak = "garak"
    promptfoo = "promptfoo"
    duke_probe = "duke_probe"


class SafetyFinding(BaseModel):
    """
    One probe outcome for reviewers (maps to ``safety_findings``).

    ``passed: true`` means the model resisted the probe (or gateway blocked
    a jailbreak attempt — see ``exporters/promptfoo.py``).
    """

    id: str
    category: str
    source: str
    passed: bool
    severity: SafetySeverity
    title: str
    description: str
    probe_id: str
    probe_suite: str | None = None
    # populated at merge time when garak + promptfoo fail same category
    corroborated_by: list[str] | None = None


class SafetyRunResult(BaseModel):
    """
    One tool run / probe suite (maps to ``safety_runs``).

    ``summary_pass_rate`` is the fraction of ``findings`` with ``passed=true``
    for this suite only (garak: per module, not per attempt).
    """

    gateway_model_id: str
    status: str = "complete"
    deployment_context: dict[str, Any] = Field(default_factory=dict)
    probe_suite: str
    summary_pass_rate: float = 0.0
    tool_results: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str
    findings: list[SafetyFinding] = Field(default_factory=list)


class SafetyRunSummary(BaseModel):
    """Lightweight row for merged label — one entry per probe suite in ``runs[]``."""

    probe_suite: str
    summary_pass_rate: float
    n_findings: int
    n_passed: int
    source: str
    probe_ids: list[str] = Field(default_factory=list)


class MergedSafetyResult(BaseModel):
    """
    Combined safety label for one gateway model (week-3 JSON on disk).

    Analogous to ``ScanResult`` after ``risk_scorer``: multiple tool runs merged
    into one reviewer-facing document for the nutrition label ``safety`` pillar.
    """

    gateway_model_id: str
    display_name: str | None = None
    status: str = "complete"
    deployment_context: dict[str, Any] = Field(default_factory=dict)
    summary_pass_rate: float = 0.0
    # Duke policy headline tier (promptfoo_duke_policy_v1 failures only)
    safety_tier: SafetySeverity = SafetySeverity.low
    # garak + promptfoo red-team worst failed severity
    adversarial_tier: SafetySeverity = SafetySeverity.low
    # Calibrated headline tier: weighted pass rate across suites, escalated by
    # curated Duke policy failures (see safety/safety_scorer.py for calibration).
    composite_tier: SafetySeverity = SafetySeverity.low
    composite_score: float = 0.0
    # Suites expected but absent from this merge (skipped/failed runs).
    missing_suites: list[str] = Field(default_factory=list)
    runs: list[SafetyRunSummary] = Field(default_factory=list)
    findings: list[SafetyFinding] = Field(default_factory=list)
    tool_results: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    completed_at: str | None = None


def coerce_severity(value: str | SafetySeverity) -> SafetySeverity:
    """Safe cast for merge tier logic when exporters emit plain strings."""
    if isinstance(value, SafetySeverity):
        return value
    try:
        return SafetySeverity(str(value).lower())
    except ValueError:
        return SafetySeverity.medium
