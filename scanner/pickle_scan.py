"""modelscan whole-repo scan + fickling deep dive on pickle weight files."""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any

from scanner.paths import PICKLE_WEIGHT_NAMES

# fickling Severity isn't hashable — rank by name (string names from fickling)
SEVERITY_RANK = {
    "LIKELY_SAFE": 0,
    "POSSIBLY_UNSAFE": 1,
    "LIKELY_UNSAFE": 2,
    "LIKELY_OVERTLY_MALICIOUS": 3,
}


def find_pickle_weights(model_dir: Path) -> Path | None:
    # safetensors-only repos won't have any of these
    for name in PICKLE_WEIGHT_NAMES:
        path = model_dir / name
        if path.is_file():
            return path
    return None


def run_modelscan(model_dir: Path) -> dict[str, Any]:
    from modelscan.modelscan import ModelScan  # heavy — only when scanning

    return ModelScan().scan(str(model_dir))


def load_pytorch_pickle(bin_path: Path) -> tuple[str, list]:
    from fickling.fickle import Pickled, StackedPickle
    # legacy: stacked pickles in .bin; newer: zip with data.pkl inside
    if zipfile.is_zipfile(bin_path):
        with zipfile.ZipFile(bin_path) as zf:
            names = [n for n in zf.namelist() if n.endswith("data.pkl")]
            if not names:
                raise ValueError(f"no data.pkl in {bin_path}")
            with zf.open(names[0]) as handle:
                return "pytorch_zip", [Pickled.load(handle)]

    with bin_path.open("rb") as handle:
        stacked = StackedPickle.load(handle)
    if stacked:
        return "pytorch_stacked_pickle", list(stacked)

    with bin_path.open("rb") as handle:
        return "raw_pickle", [Pickled.load(handle)]


def analyze_pytorch_bin(bin_path: Path) -> dict[str, Any]:
    from fickling.analysis import Severity, check_safety

    fmt, pickles = load_pytorch_pickle(bin_path)
    severities = [check_safety(p).severity for p in pickles]
    worst = max(severities, key=lambda s: SEVERITY_RANK[s.name])

    return {
        "file": str(bin_path),
        "pytorch_format": fmt,
        "stack_count": len(pickles),
        "is_likely_safe": all(s == Severity.LIKELY_SAFE for s in severities),
        "severity": worst.name,
        "ast_node_count": sum(len(p.ast.body) for p in pickles),
    }


def run_fickling_if_applicable(model_dir: Path) -> dict[str, Any] | None:
    bin_file = find_pickle_weights(model_dir)
    if not bin_file:
        return None
    return analyze_pytorch_bin(bin_file)


def modelscan_tier(modelscan_payload: dict[str, Any]) -> str:
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    if counts.get("CRITICAL", 0):
        return "critical"
    if counts.get("HIGH", 0):
        return "high"
    if counts.get("MEDIUM", 0):
        return "medium"
    return "low"


def modelscan_summary_trimmed(modelscan_payload: dict[str, Any]) -> dict[str, Any]:
    # keep counts + scanned list; full skipped paths stay in raw payload / gap_map
    summary = modelscan_payload.get("summary", {})
    skipped = summary.get("skipped", {})
    scanned = summary.get("scanned", {})
    return {
        "total_issues_by_severity": summary.get("total_issues_by_severity", {}),
        "total_issues": summary.get("total_issues", 0),
        "modelscan_version": summary.get("modelscan_version"),
        "scanned_files": scanned.get("scanned_files", []),
        "total_skipped": skipped.get("total_skipped", 0),
    }
