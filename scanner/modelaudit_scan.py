"""
ModelAudit integration — content-routed scan of candidate model byte files.

Why this layer exists (see ``docs/tool-stack.md``):
  - ModelScan routes by extension and may skip ``.bin``/``.pt`` or never open a path.
  - Fickling only runs on discovered pickle-family paths.
  - ModelAudit inspects file *content* (magic bytes, 45+ format scanners), so renamed or
    extensionless malicious payloads still get analyzed (e.g. extension-mismatch PoCs).

Overlapping findings with ModelScan/Fickling are expected; ``risk_scorer`` dedupes them.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from scanner.format_detector import FileFormatSummary

# When ModelScan already reported issues, these pickle partial-scan rules are noise.
_PICKLE_NOISE_RULES = frozenset({"S901", "S902", "S212"})

_TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Never treat these as weight/tensor streams (configs, docs, tokenizer vocab, code).
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

_NON_MODEL_BASENAMES = frozenset({
    "merges.txt",
    "vocab.txt",
    "README.md",
    "LICENSE",
    "LICENSE.txt",
})


def _should_skip_path(rel_path: str) -> bool:
    """
    Return True if this repo-relative path cannot be a model artifact.

    Extensionless files are NOT skipped — ModelAudit may still detect pickle inside.
    """
    lower = rel_path.lower()
    name = Path(lower).name
    if name in _NON_MODEL_BASENAMES:
        return True
    suffix = Path(lower).suffix
    if suffix in _NON_MODEL_SUFFIXES:
        return True
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
    List every on-disk file that might be a model byte stream for ModelAudit CLI.

    Includes paths ModelScan already scanned and paths Fickling already analyzed —
    ModelAudit's internal routers decide applicability. Optional args reserved for
    future narrowing; currently scans all non-skipped files under ``model_dir``.
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
    """Invoke ``python -m modelaudit scan`` and parse JSON stdout."""
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
    """Extract file path from a ModelAudit issue dict."""
    return str(issue.get("location") or issue.get("file") or "")


def normalize_issue_path(loc: str) -> str:
    """
    Normalize ModelAudit location strings for cross-tool dedupe in ``risk_scorer``.

    Strips byte-offset suffixes like ``' (pos 76)'`` so Fickling and ModelAudit align.
    """
    if " (pos " in loc:
        return loc.split(" (pos ", 1)[0].strip()
    return loc.strip()


def _issue_signal_key(issue: dict[str, Any]) -> str:
    """Stable key fragment for dedupe: import global, rule code, or message stem."""
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
    """True if the issue describes pickle deserialization risk (not generic format warn)."""
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
    """True for optional-scanner install hints (ONNX/H5 backends not installed)."""
    msg = (issue.get("message") or "").lower()
    return "not installed" in msg or "install with" in msg


def is_actionable_modelaudit_issue(
    issue: dict[str, Any], *, modelscan_total_issues: int
) -> bool:
    """
    Decide whether an issue should affect the nutrition label.

    Filters:
      - Install-missing optional backend messages
      - Pickle partial-scan rules S901/S902 when ModelScan already found issues
      - Low-severity pickle noise unless message explicitly indicates exploit patterns

    Non-pickle formats: medium+ severities are actionable.
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
    """
    Run ModelAudit on all candidate files; return summary for ``tool_results``.

    Raises ImportError if ``modelaudit`` package is not installed (required in Docker image).
    Caps stored actionable issues at 50; full counts remain in ``issue_count``.
    """
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
    """Worst severity tier among actionable ModelAudit issues (for ``risk_scorer``)."""
    if not summary or not summary.get("issues"):
        return "low"
    worst = "low"
    for issue in summary["issues"]:
        sev = (issue.get("severity") or "low").lower()
        if sev in _TIER_ORDER and _TIER_ORDER[sev] > _TIER_ORDER[worst]:
            worst = sev
    return worst
