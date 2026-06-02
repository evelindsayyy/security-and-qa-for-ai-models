"""
ModelAudit on weight formats ModelScan skips (safetensors, ONNX).

Pickle weights are intentionally excluded here — ModelScan + Fickling own that path
to avoid duplicate false positives (S902 partial-scan noise on pytorch_model.bin).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scanner.format_detector import FileFormatSummary

# Pickle-bin noise when ModelScan is clean (experiment-backed)
_PICKLE_NOISE_RULES = frozenset({"S901", "S902", "S212"})

_TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def collect_modelaudit_targets(
    model_dir: Path, format_summary: FileFormatSummary
) -> list[Path]:
    """Paths worth a second opinion: safetensors + onnx only."""
    targets: list[Path] = []
    for rel in format_summary.by_category.get("safetensors", []):
        p = model_dir / rel
        if p.is_file():
            targets.append(p)
    for rel in format_summary.by_category.get("onnx", []):
        p = model_dir / rel
        if p.is_file():
            targets.append(p)
    return sorted(targets)


def _run_cli(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        return {"issues": [], "bytes_scanned": 0}

    cmd = [
        sys.executable,
        "-m",
        "modelaudit",
        "scan",
        *[str(p) for p in paths],
        "--format",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    if not stdout:
        raise RuntimeError(
            f"modelaudit failed (exit {proc.returncode}): {proc.stderr[-1500:]}"
        )
    return json.loads(stdout[stdout.find("{") :])


def _issue_location(issue: dict[str, Any]) -> str:
    return str(issue.get("location") or issue.get("file") or "")


def _is_safetensors_path(loc: str) -> bool:
    return ".safetensors" in loc.lower()


def _is_onnx_path(loc: str) -> bool:
    lower = loc.lower()
    return lower.endswith(".onnx") or ".onnx" in lower


def _install_missing_noise(issue: dict[str, Any]) -> bool:
    msg = (issue.get("message") or "").lower()
    return "not installed" in msg or "install with" in msg


def is_actionable_modelaudit_issue(
    issue: dict[str, Any], *, modelscan_total_issues: int
) -> bool:
    """
    Filter spike noise: only elevate on real signals for st/onnx;
    never treat pickle-bin scanner limits as findings when ModelScan is clean.
    """
    sev = (issue.get("severity") or "").lower()
    loc = _issue_location(issue)
    rule = str(issue.get("rule_code") or "")

    if _install_missing_noise(issue):
        return False

    if _is_safetensors_path(loc) or _is_onnx_path(loc):
        return sev in ("critical", "high", "medium")

    # pickle paths should not be in scoped scan; guard anyway
    if any(x in loc for x in (".bin", ".pt", ".pth")):
        if modelscan_total_issues == 0 and rule in _PICKLE_NOISE_RULES:
            return False
        return sev in ("critical", "high")

    return sev in ("critical", "high")


def run_modelaudit_scoped(
    model_dir: Path, format_summary: FileFormatSummary, modelscan_payload: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Run ModelAudit on safetensors/onnx targets. Returns summary dict for tool_results,
    or None if modelaudit not installed / no targets.
    """
    try:
        import modelaudit  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "modelaudit required for scan pipeline — pip install modelaudit"
        ) from exc

    targets = collect_modelaudit_targets(model_dir, format_summary)
    ms_issues = modelscan_payload.get("summary", {}).get("total_issues", 0)
    if not targets:
        return {
            "paths_scanned": [],
            "issue_count": 0,
            "actionable_issue_count": 0,
            "by_severity": {},
            "issues": [],
            "note": "no safetensors/onnx files to scan",
        }

    raw = _run_cli(targets)
    issues = raw.get("issues") or []
    actionable = [
        i for i in issues if is_actionable_modelaudit_issue(i, modelscan_total_issues=ms_issues)
    ]

    by_sev: dict[str, int] = {}
    for issue in issues:
        sev = (issue.get("severity") or "unknown").lower()
        by_sev[sev] = by_sev.get(sev, 0) + 1

    return {
        "paths_scanned": [str(p.relative_to(model_dir)) for p in targets],
        "bytes_scanned": raw.get("bytes_scanned"),
        "issue_count": len(issues),
        "actionable_issue_count": len(actionable),
        "by_severity": by_sev,
        "issues": actionable[:50],
        "noise_filtered_count": len(issues) - len(actionable),
    }


def modelaudit_tier(summary: dict[str, Any] | None) -> str:
    """Worst tier implied by actionable ModelAudit issues only."""
    if not summary or not summary.get("issues"):
        return "low"
    worst = "low"
    for issue in summary["issues"]:
        sev = (issue.get("severity") or "low").lower()
        if sev in _TIER_ORDER and _TIER_ORDER[sev] > _TIER_ORDER[worst]:
            worst = sev
    return worst
