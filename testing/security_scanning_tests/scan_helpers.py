"""
shared helpers for the security scanning spike scripts.

keeps modelscan + fickling logic in one place so run_*.py stay short.
"""

import json
import zipfile
from pathlib import Path

from fickling.analysis import Severity, check_safety
from fickling.fickle import Pickled


def load_pytorch_bin_pickle(bin_path: Path) -> Pickled:
    """
    pytorch .bin files are zip archives, not raw pickle files.
    pull out the inner data.pkl and parse that with fickling.
    """
    with zipfile.ZipFile(bin_path, "r") as zf:
        pkl_names = [name for name in zf.namelist() if name.endswith("data.pkl")]
        if not pkl_names:
            raise ValueError(f"no data.pkl found inside {bin_path}")

        # distilbert uses archive/data.pkl — first match is fine
        with zf.open(pkl_names[0]) as handle:
            return Pickled.load(handle)


def analyze_pickle(pickled: Pickled) -> dict:
    """run fickling safety checks and return a json-friendly dict."""
    results = check_safety(pickled)

    # count ast node types — handy when documenting what fickling exposes
    node_types: dict[str, int] = {}
    for node in pickled.ast.body:
        name = type(node).__name__
        node_types[name] = node_types.get(name, 0) + 1

    return {
        "is_likely_safe": results.severity == Severity.LIKELY_SAFE,
        "severity": results.severity.name,
        "ast_node_count": len(pickled.ast.body),
        "ast_node_types": node_types,
        "analysis_summary": results.to_string(),
    }


def run_modelscan(model_dir: Path) -> dict:
    """
    call modelscan via its python api (not cli).

    the cli flags changed in newer modelscan versions (--output-format is gone).
    the api returns a stable dict with summary + issues + errors.
    """
    from modelscan.modelscan import ModelScan

    scanner = ModelScan()
    return scanner.scan(str(model_dir))


def format_modelscan_text(payload: dict) -> str:
    """build a plain-text report from modelscan api output (no emojis)."""
    summary = payload.get("summary", {})
    lines = [
        "--- modelscan summary ---",
        "",
    ]

    counts = summary.get("total_issues_by_severity", {})
    for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        lines.append(f"  {severity}: {counts.get(severity, 0)}")

    lines.append(f"  total issues: {summary.get('total_issues', 0)}")
    lines.append(f"  input path: {summary.get('input_path', 'unknown')}")

    issues = payload.get("issues", [])
    lines.append("")
    if issues:
        lines.append("--- issues ---")
        for issue in issues:
            desc = issue.get("description", str(issue))
            source = issue.get("source", "")
            lines.append(f"  - [{source}] {desc}")
    else:
        lines.append("no issues found")

    skipped = summary.get("skipped", {})
    total_skipped = skipped.get("total_skipped", 0)
    lines.append("")
    lines.append(f"skipped files: {total_skipped}")
    lines.append("(run modelscan with --show-skipped on cli to see full list)")

    errors = payload.get("errors", [])
    if errors:
        lines.append("")
        lines.append("--- errors ---")
        for err in errors:
            lines.append(f"  - {err}")

    return "\n".join(lines)


def severity_tier(modelscan_payload: dict) -> str:
    """map modelscan severity counts -> low/medium/high/critical."""
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    if counts.get("CRITICAL", 0) > 0:
        return "critical"
    if counts.get("HIGH", 0) > 0:
        return "high"
    if counts.get("MEDIUM", 0) > 0:
        return "medium"
    return "low"


def dump_json(path: Path, data: dict) -> None:
    """write pretty json to a bind-mounted output path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
