"""shared helpers — modelscan api + fickling on pytorch .bin files."""

import json
import zipfile
from pathlib import Path

from fickling.analysis import Severity, check_safety
from fickling.fickle import Pickled, StackedPickle

# worst severity wins when a .bin has multiple stacked pickles
# use .name — Severity enum isn't hashable in this fickling version
SEVERITY_RANK = {
    "LIKELY_SAFE": 0,
    "POSSIBLY_UNSAFE": 1,
    "LIKELY_UNSAFE": 2,
    "LIKELY_OVERTLY_MALICIOUS": 3,
}


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def run_modelscan(model_dir: Path) -> dict:
    # python api — newer modelscan dropped cli json flags
    from modelscan.modelscan import ModelScan

    return ModelScan().scan(str(model_dir))


def load_pytorch_pickle(bin_path: Path) -> tuple[str, list[Pickled]]:
    # modern .bin = zip with data.pkl inside
    if zipfile.is_zipfile(bin_path):
        with zipfile.ZipFile(bin_path) as zf:
            names = [n for n in zf.namelist() if n.endswith("data.pkl")]
            if not names:
                raise ValueError(f"no data.pkl in {bin_path}")
            with zf.open(names[0]) as handle:
                return "pytorch_zip", [Pickled.load(handle)]

    # legacy .bin = stacked pickles (distilbert uses this)
    with bin_path.open("rb") as handle:
        stacked = StackedPickle.load(handle)
    if stacked:
        return "pytorch_stacked_pickle", list(stacked)

    # fallback — single raw pickle
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


def severity_tier(modelscan_payload: dict) -> str:
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    if counts.get("CRITICAL", 0):
        return "critical"
    if counts.get("HIGH", 0):
        return "high"
    if counts.get("MEDIUM", 0):
        return "medium"
    return "low"


def format_modelscan_text(payload: dict) -> str:
    summary = payload.get("summary", {})
    counts = summary.get("total_issues_by_severity", {})
    lines = [f"total issues: {summary.get('total_issues', 0)}"]
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        lines.append(f"  {level}: {counts.get(level, 0)}")
    if not payload.get("issues"):
        lines.append("no issues found")
    return "\n".join(lines)
