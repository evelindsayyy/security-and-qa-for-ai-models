"""
ModelAudit — content-routed scan of every candidate file in a model directory.

ModelScan routes by extension and may skip .bin/.pt or never open a file.
Fickling analyzes pickle AST on discovered pickle-family paths.
ModelAudit uses magic-byte / structural detection (45+ scanners) so renamed or
extensionless artifacts still reach the right scanner — see extension-mismatch PoCs.

Overlap with ModelScan/Fickling is intentional (defense-in-depth);
the risk scorer dedupes correlated findings.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scanner.format_detector import FileFormatSummary

# ModelScan "clean" + these rules on pickle paths = partial-scan noise, not threats
_PICKLE_NOISE_RULES = frozenset({"S901", "S902", "S212"})

_TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Files we never send to ModelAudit (configs, docs, source — not model bytes)
_NON_MODEL_SUFFIXES = frozenset({
    ".json",
    ".txt",
    ".md",
    ".py",
    ".cpp",
    ".c",
    ".h",
    ".cu",
    ".rs",
    ".go",
    ".gitattributes",
    ".jinja",
    ".j2",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".csv",
    ".tsv",
    ".html",
    ".css",
    ".sh",
    ".bat",
    ".ps1",
})

# Basename patterns that are never weight artifacts (tokenizer vocab, etc.)
_NON_MODEL_BASENAMES = frozenset({
    "merges.txt",
    "vocab.txt",
    "README.md",
    "LICENSE",
    "LICENSE.txt",
})


def _should_skip_path(rel_path: str) -> bool:
    """
    Return True if this path cannot be a model artifact (speed + fewer FP configs).

    Extensionless files are NOT skipped — ModelAudit may detect pickle inside.
    """
    lower = rel_path.lower()
    name = Path(lower).name
    if name in _NON_MODEL_BASENAMES:
        return True
    suffix = Path(lower).suffix
    if suffix in _NON_MODEL_SUFFIXES:
        return True
    # Hugging Face tokenizer spiece — not a weight tensor file
    if suffix == ".model" and "spiece" in lower:
        return True
    return False


def collect_modelaudit_targets(
    model_dir: Path,
    format_summary: FileFormatSummary | None = None,
    modelscan_payload: dict[str, Any] | None = None,
    fickling_report: dict[str, Any] | None = None,
) -> list[Path]:
    """
    Every file under model_dir that might be a model byte stream.

    Includes paths ModelScan already scanned and paths Fickling already analyzed.
    ModelAudit content detection decides whether a file is in scope.
    """
    _ = format_summary, modelscan_payload, fickling_report

    targets: list[Path] = []
    for path in sorted(model_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(model_dir))
        if rel.startswith(".cache"):
            continue
        if _should_skip_path(rel):
            continue
        targets.append(path)
    return targets


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


def normalize_issue_path(loc: str) -> str:
    """Strip ModelAudit suffix like ' (pos 76)' for cross-tool matching."""
    if " (pos " in loc:
        return loc.split(" (pos ", 1)[0].strip()
    return loc.strip()


def _issue_signal_key(issue: dict[str, Any]) -> str:
    """Stable key for dedupe: dangerous global, rule, or message stem."""
    details = issue.get("details") or {}
    if isinstance(details, dict):
        imp = details.get("import_reference") or details.get("associated_global")
        if imp:
            return str(imp).lower()
        rule = details.get("pickle_rule_code") or details.get("rule_code")
        if rule:
            return str(rule).lower()
    rule = issue.get("rule_code")
    if rule:
        return str(rule).lower()
    msg = (issue.get("message") or "")[:120].lower()
    return msg


def _is_pickle_family_signal(issue: dict[str, Any], loc: str) -> bool:
    """True if issue describes pickle deserialization risk."""
    lower = (loc + " " + (issue.get("message") or "") + " " + str(issue.get("type") or "")).lower()
    if issue.get("type") == "pickle_check":
        return True
    pickle_hints = (
        "pickle",
        "reduce opcode",
        "dangerous global",
        "dill",
        "joblib",
        "serialization",
    )
    return any(h in lower for h in pickle_hints)


def _install_missing_noise(issue: dict[str, Any]) -> bool:
    msg = (issue.get("message") or "").lower()
    return "not installed" in msg or "install with" in msg


def is_actionable_modelaudit_issue(
    issue: dict[str, Any], *, modelscan_total_issues: int
) -> bool:
    """
    Drop install-missing ONNX/H5 noise; drop S901/S902 partial-scan on pickle
    only when ModelScan already reported issues on this repo.

    Real pickle/globals: critical/high always; medium when message is explicit.
    Other formats: medium+ is actionable.
    """
    sev = (issue.get("severity") or "").lower()
    loc = _issue_location(issue)
    rule = str(issue.get("rule_code") or "")

    if _install_missing_noise(issue):
        return False

    if _is_pickle_family_signal(issue, loc):
        if modelscan_total_issues > 0 and rule in _PICKLE_NOISE_RULES:
            return False
        if sev in ("critical", "high"):
            return True
        if sev == "medium" and any(
            k in (issue.get("message") or "").lower()
            for k in ("unsafe", "malicious", "dangerous", "suspicious", "reduce")
        ):
            return True
        return False

    return sev in ("critical", "high", "medium")


def run_modelaudit_scoped(
    model_dir: Path,
    format_summary: FileFormatSummary,
    modelscan_payload: dict[str, Any],
    fickling_report: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run ModelAudit on all candidate files; content routing inside ModelAudit."""
    try:
        import modelaudit  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "modelaudit required for scan pipeline — pip install modelaudit"
        ) from exc

    targets = collect_modelaudit_targets(
        model_dir, format_summary, modelscan_payload, fickling_report
    )
    ms_issues = modelscan_payload.get("summary", {}).get("total_issues", 0)
    modelscan_skipped = (
        modelscan_payload.get("summary", {}).get("skipped", {}).get("total_skipped", 0)
    )
    if not targets:
        return {
            "paths_scanned": [],
            "issue_count": 0,
            "actionable_issue_count": 0,
            "by_severity": {},
            "issues": [],
            "note": "no scannable files under model directory",
            "modelscan_skipped_count": modelscan_skipped,
            "scan_mode": "content_routed",
        }

    raw = _run_cli(targets)
    issues = raw.get("issues") or []
    actionable = [
        i
        for i in issues
        if is_actionable_modelaudit_issue(i, modelscan_total_issues=ms_issues)
    ]

    by_sev: dict[str, int] = {}
    for issue in issues:
        sev = (issue.get("severity") or "unknown").lower()
        by_sev[sev] = by_sev.get(sev, 0) + 1

    return {
        "paths_scanned": [str(p.relative_to(model_dir)) for p in targets],
        "path_count": len(targets),
        "bytes_scanned": raw.get("bytes_scanned"),
        "issue_count": len(issues),
        "actionable_issue_count": len(actionable),
        "by_severity": by_sev,
        "issues": actionable[:50],
        "noise_filtered_count": len(issues) - len(actionable),
        "modelscan_skipped_count": modelscan_skipped,
        "scan_mode": "content_routed",
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
