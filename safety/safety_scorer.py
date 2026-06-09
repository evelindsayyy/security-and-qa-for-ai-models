"""
Merge multiple ``SafetyRunResult`` documents into one ``MergedSafetyResult``.

Policy layer between per-tool exports and the nutrition-label ``safety`` pillar —
analogous to ``scanner/risk_scorer.py`` for ModelScan + Fickling + ModelAudit.

Precedence:
  - ``safety_tier`` = max severity among **failed** findings (passed rows ignored)
  - ``summary_pass_rate`` = fraction of all merged findings with ``passed=true``
  - Each ``probe_suite`` stays a separate logical ``safety_runs`` row in ``runs[]``

Defense-in-depth: if garak and promptfoo both fail the same ``category`` with
high/critical severity, tag ``corroborated_by`` on the primary finding.
"""

from __future__ import annotations

from typing import Any

from safety.gateway_ids import display_name_from_id, normalize_gateway_model_id
from safety.schemas import (
    MergedSafetyResult,
    SafetyFinding,
    SafetyRunResult,
    SafetyRunSummary,
    SafetySeverity,
    coerce_severity,
)

_SEVERITY_RANK = {
    SafetySeverity.low: 0,
    SafetySeverity.medium: 1,
    SafetySeverity.high: 2,
    SafetySeverity.critical: 3,
}


def _max_severity(a: SafetySeverity, b: SafetySeverity) -> SafetySeverity:
    return a if _SEVERITY_RANK[a] >= _SEVERITY_RANK[b] else b


def _worst_failed_tier(findings: list[SafetyFinding]) -> SafetySeverity:
    tier = SafetySeverity.low
    for f in findings:
        if not f.passed:
            tier = _max_severity(tier, coerce_severity(f.severity))
    return tier


def _corroborate_cross_tool(findings: list[SafetyFinding]) -> list[SafetyFinding]:
    """
    Mark cross-tool agreement on the same category when both failed.

    Primary source order: promptfoo (Duke policy) > garak (broad probes).
    """
    failed_by_cat: dict[str, list[SafetyFinding]] = {}
    for f in findings:
        if not f.passed:
            failed_by_cat.setdefault(f.category, []).append(f)

    corro_map: dict[str, list[str]] = {}
    for group in failed_by_cat.values():
        sources = sorted({f.source for f in group})
        if len(sources) < 2:
            continue
        for f in group:
            others = [s for s in sources if s != f.source]
            if others:
                corro_map[f.id] = others

    if not corro_map:
        return findings

    out: list[SafetyFinding] = []
    for f in findings:
        if f.id in corro_map:
            out.append(f.model_copy(update={"corroborated_by": corro_map[f.id]}))
        else:
            out.append(f)
    return out


def merge_safety_runs(runs: list[SafetyRunResult | dict[str, Any]]) -> MergedSafetyResult:
    """
    Combine one or more validated tool runs for the same gateway model.

    Raises ``ValueError`` if runs reference different ``gateway_model_id`` values
    after normalization.
    """
    parsed: list[SafetyRunResult] = []
    for r in runs:
        if isinstance(r, dict):
            raw_id = r.get("gateway_model_id", "")
            r = dict(r)
            r["gateway_model_id"] = normalize_gateway_model_id(str(raw_id))
            parsed.append(SafetyRunResult.model_validate(r))
        else:
            parsed.append(
                r.model_copy(
                    update={"gateway_model_id": normalize_gateway_model_id(r.gateway_model_id)}
                )
            )

    if not parsed:
        raise ValueError("At least one SafetyRunResult is required")

    gateway_ids = {r.gateway_model_id for r in parsed}
    if len(gateway_ids) > 1:
        raise ValueError(f"Cannot merge runs for different models: {sorted(gateway_ids)}")

    gateway_model_id = parsed[0].gateway_model_id
    deployment_context = parsed[0].deployment_context

    summaries: list[SafetyRunSummary] = []
    all_findings: list[SafetyFinding] = []
    tool_results: dict[str, Any] = {}
    started_at: str | None = None
    completed_at: str | None = None

    for run in parsed:
        n = len(run.findings)
        n_passed = sum(1 for f in run.findings if f.passed)
        primary_source = run.findings[0].source if run.findings else "unknown"
        probe_ids = sorted({f.probe_id for f in run.findings if f.probe_id})
        summaries.append(
            SafetyRunSummary(
                probe_suite=run.probe_suite,
                summary_pass_rate=run.summary_pass_rate,
                n_findings=n,
                n_passed=n_passed,
                source=primary_source,
                probe_ids=probe_ids,
            )
        )
        all_findings.extend(run.findings)
        tool_results[run.probe_suite] = run.tool_results
        if run.started_at and (started_at is None or run.started_at < started_at):
            started_at = run.started_at
        if run.completed_at and (completed_at is None or run.completed_at > completed_at):
            completed_at = run.completed_at

    all_findings = _corroborate_cross_tool(all_findings)
    total = len(all_findings)
    passed = sum(1 for f in all_findings if f.passed)
    summary_pass_rate = round((passed / total) if total else 0.0, 4)

    merged = MergedSafetyResult(
        gateway_model_id=gateway_model_id,
        display_name=display_name_from_id(gateway_model_id),
        status="complete",
        deployment_context=deployment_context,
        summary_pass_rate=summary_pass_rate,
        safety_tier=_worst_failed_tier(all_findings),
        runs=summaries,
        findings=all_findings,
        tool_results=tool_results,
        started_at=started_at,
        completed_at=completed_at,
    )
    return merged
