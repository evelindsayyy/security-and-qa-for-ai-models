"""
shared helpers for security scanning tests.

modelscan = scans the whole model folder for unsafe pickle ops
fickling = deep dive on the pickle inside pytorch_model.bin

set MODEL_ID env var to scan a different hugging face repo (default: distilbert-base-uncased)
"""

import json
import os
import zipfile
from pathlib import Path

from fickling.analysis import Severity, check_safety
from fickling.fickle import Pickled, StackedPickle

DEFAULT_MODEL_ID = "distilbert-base-uncased"
MODELS_ROOT = Path("/models")

# filenames we check for pickle-based weights (fickling target)
PICKLE_WEIGHT_NAMES = ("pytorch_model.bin", "model.bin", "pytorch_model.pt", "model.pt")

# fickling Severity enum isn't hashable — rank by name string instead
SEVERITY_RANK = {
    "LIKELY_SAFE": 0,
    "POSSIBLY_UNSAFE": 1,
    "LIKELY_UNSAFE": 2,
    "LIKELY_OVERTLY_MALICIOUS": 3,
}


def get_model_id() -> str:
    # e.g. MODEL_ID=gpt2 or MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
    return os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)


def get_model_dir(model_id: str | None = None) -> Path:
    return MODELS_ROOT / (model_id or get_model_id())


def output_dir(model_id: str | None = None) -> Path:
    # one subfolder per model so runs don't overwrite each other
    safe_name = (model_id or get_model_id()).replace("/", "--")
    return Path("/output") / safe_name


def find_pickle_weights(model_dir: Path) -> Path | None:
    # fickling needs a pickle weights file — safetensors-only repos have no target
    for name in PICKLE_WEIGHT_NAMES:
        path = model_dir / name
        if path.is_file():
            return path
    return None


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def run_modelscan(model_dir: Path) -> dict:
    # use python api — cli json flags changed in modelscan 0.8+
    from modelscan.modelscan import ModelScan

    return ModelScan().scan(str(model_dir))


def load_pytorch_pickle(bin_path: Path) -> tuple[str, list[Pickled]]:
    # distilbert .bin = legacy stacked pickles (not a zip)
    # newer models = zip with data.pkl inside
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


def analyze_pytorch_bin(bin_path: Path) -> dict:
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


def modelscan_tier(modelscan_payload: dict) -> str:
    # maps modelscan issue counts -> low/medium/high/critical
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    if counts.get("CRITICAL", 0):
        return "critical"
    if counts.get("HIGH", 0):
        return "high"
    if counts.get("MEDIUM", 0):
        return "medium"
    return "low"


def modelscan_summary_trimmed(modelscan_payload: dict) -> dict:
    # combined report gets counts only — full skipped list stays in modelscan_report.json
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
    lines.append("(full skipped list in modelscan_report.json)")
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
    # legit pytorch models often get LIKELY_UNSAFE here — not necessarily an exploit
    if not report["is_likely_safe"]:
        lines.append("")
        lines.append(
            "note: fickling often flags benign pytorch weight pickles as LIKELY_UNSAFE. "
            "treat as a signal, not a final verdict — production scanner will merge both tools."
        )
    return "\n".join(lines)
