"""human-readable summaries for cli / debug (optional)."""


def format_modelscan_text(payload: dict) -> str:
    summary = payload.get("summary", {})
    counts = summary.get("total_issues_by_severity", {})
    lines = [f"total issues: {summary.get('total_issues', 0)}"]
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        lines.append(f"  {level}: {counts.get(level, 0)}")
    if not payload.get("issues"):
        lines.append("no issues found")
    skipped = summary.get("skipped", {})
    lines.append(f"skipped files: {skipped.get('total_skipped', 0)}")
    lines.append("(full detail in modelscan_report.json)")
    return "\n".join(lines)


def format_fickling_text(report: dict) -> str:
    lines = [
        f"file: {report['file']}",
        f"pytorch_format: {report['pytorch_format']}",
        f"stack_count: {report['stack_count']}",
        f"severity: {report['severity']}",
        f"is_likely_safe: {report['is_likely_safe']}",
        f"ast_node_count: {report['ast_node_count']}",
    ]
    if not report["is_likely_safe"]:
        lines.append("")
        lines.append(
            "note: fickling often flags benign pytorch pickles as LIKELY_UNSAFE — "
            "merge with modelscan in risk_scorer, not a solo deploy block."
        )
    return "\n".join(lines)


def format_modelaudit_text(report: dict) -> str:
    """ModelAudit summary (content-routed; defense-in-depth with other tools)."""
    paths = report.get("paths_scanned") or []
    lines = [
        f"paths_scanned: {len(paths)}",
        *(f"  - {p}" for p in paths[:12]),
        f"raw issues: {report.get('issue_count', 0)}",
        f"actionable (risk scorer): {report.get('actionable_issue_count', 0)}",
        f"noise filtered: {report.get('noise_filtered_count', 0)}",
    ]
    by_sev = report.get("by_severity") or {}
    if by_sev:
        lines.append("by_severity: " + ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())))
    if report.get("note"):
        lines.append(f"note: {report['note']}")
    mode = report.get("scan_mode", "content_routed")
    lines.append(f"scan_mode: {mode}")
    if not paths:
        lines.append("(no candidate files)")
    lines.append("(detail: modelaudit_report.json)")
    return "\n".join(lines)
