"""
glue modelscan + fickling into one json report.

this shape is close to what scanner/ will eventually produce (see docs/scanner-output-format.md).

run inside the container (after download_model.py, or after the other two scripts):
    python run_combined_scan.py

writes:
    /output/combined_scan.json
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import fickling

MODEL_ID = "distilbert-base-uncased"
MODEL_DIR = Path("/models") / MODEL_ID
BIN_FILE = MODEL_DIR / "pytorch_model.bin"
OUTPUT_DIR = Path("/output")
COMBINED_OUT = OUTPUT_DIR / "combined_scan.json"


def run_modelscan(model_dir: Path) -> dict:
    """call modelscan cli and return parsed json (or error dict)."""
    result = subprocess.run(
        ["modelscan", "scan", "-p", str(model_dir), "--output-format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.stdout:
        return {"error": result.stderr.strip()}
    return json.loads(result.stdout)


def run_fickling(bin_file: Path) -> dict:
    """run fickling on the pickle weights file."""
    with bin_file.open("rb") as handle:
        pickled = fickling.Pickled.load(handle)
    return {
        "file": str(bin_file),
        "is_likely_safe": fickling.is_likely_safe(pickled),
        "ast_node_count": len(pickled.ast.body),
    }


def severity_tier(modelscan_payload: dict) -> str:
    """
    map modelscan severity counts -> low/medium/high/critical
    matches tiers described in CONTEXT.md
    """
    counts = modelscan_payload.get("summary", {}).get("total_issues_by_severity", {})
    if counts.get("CRITICAL", 0) > 0:
        return "critical"
    if counts.get("HIGH", 0) > 0:
        return "high"
    if counts.get("MEDIUM", 0) > 0:
        return "medium"
    return "low"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"{MODEL_DIR} not found — run download_model.py first"
        )

    print("running combined scan ...")

    # run both tools
    modelscan_payload = run_modelscan(MODEL_DIR)
    fickling_payload = run_fickling(BIN_FILE)

    # assemble report — overall_risk_score is a placeholder until we build the real scorer
    combined = {
        "model_id": MODEL_ID,
        "scanned_files": [
            "pytorch_model.bin",
            "model.safetensors",
        ],
        "overall_risk_score": 0,  # todo: real weighted rubric in scanner/
        "severity_tier": severity_tier(modelscan_payload),
        "findings": modelscan_payload.get("issues", []),
        "tool_results": {
            "modelscan": modelscan_payload.get("summary", modelscan_payload),
            "fickling": fickling_payload,
        },
        "scan_metadata": {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "scanner_version": "scanner_spike-0.1.0",
            "container_image": "testing/scanner_spike",
        },
    }

    COMBINED_OUT.write_text(json.dumps(combined, indent=2))
    print(f"wrote {COMBINED_OUT}")
    print("\ncombined report:")
    print(json.dumps(combined, indent=2))


if __name__ == "__main__":
    main()
