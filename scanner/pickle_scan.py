"""ModelScan whole-repo scan + Fickling deep dive on every pickle-family weight file."""

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

# Extensions treated as pickle/pytorch weight candidates for Fickling
_PICKLE_FAMILY_SUFFIXES = (".bin", ".pt", ".pth", ".pkl", ".pickle", ".dill", ".joblib", ".ckpt")


def _is_pickle_family_file(path: Path) -> bool:
    name = path.name
    lower = path.name.lower()
    if name in PICKLE_WEIGHT_NAMES:
        return True
    return lower.endswith(_PICKLE_FAMILY_SUFFIXES)


def find_all_pickle_weights(model_dir: Path) -> list[Path]:
    """
    All pickle-family weight files under model_dir (recursive, skip .cache).

    Defense-in-depth: sibling files like malicious_model.pt are not missed when
    pytorch_model.bin was found first.
    """
    found: list[Path] = []
    seen: set[str] = set()
    for path in sorted(model_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(model_dir))
        if rel.startswith(".cache"):
            continue
        if not _is_pickle_family_file(path):
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        found.append(path)
    return found


def find_pickle_weights(model_dir: Path) -> Path | None:
    """First pickle-family file (compat); prefer find_all_pickle_weights."""
    all_paths = find_all_pickle_weights(model_dir)
    return all_paths[0] if all_paths else None


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
    """
    Run Fickling on every pickle-family file; return aggregate + per_file list.

    Top-level severity/file/pytorch_format reflect the worst file across the repo.
    """
    paths = find_all_pickle_weights(model_dir)
    if not paths:
        return None

    per_file: list[dict[str, Any]] = []
    worst_rank = -1
    worst_report: dict[str, Any] | None = None

    for path in paths:
        try:
            report = analyze_pytorch_bin(path)
        except Exception as exc:  # noqa: BLE001 — one bad file must not abort scan
            report = {
                "file": str(path),
                "pytorch_format": "error",
                "stack_count": 0,
                "is_likely_safe": False,
                "severity": "POSSIBLY_UNSAFE",
                "ast_node_count": 0,
                "error": str(exc)[:500],
            }
        per_file.append(report)
        rank = SEVERITY_RANK.get(report["severity"], 0)
        if rank > worst_rank:
            worst_rank = rank
            worst_report = report

    assert worst_report is not None
    return {
        **worst_report,
        "files_analyzed": len(per_file),
        "per_file": per_file,
    }


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
