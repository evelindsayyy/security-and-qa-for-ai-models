"""
glue modelscan + fickling into one json report.

this shape is close to what scanner/ will eventually produce (see docs/scanner-output-format.md).

run inside the container (after download_model.py):
    python run_combined_scan.py

writes:
    /output/combined_scan.json
"""

from datetime import datetime, timezone
from pathlib import Path

from scan_helpers import (
    analyze_pickle,
    dump_json,
    load_pytorch_bin_pickle,
    run_modelscan,
    severity_tier,
)

MODEL_ID = "distilbert-base-uncased"
MODEL_DIR = Path("/models") / MODEL_ID
BIN_FILE = MODEL_DIR / "pytorch_model.bin"
OUTPUT_DIR = Path("/output")
COMBINED_OUT = OUTPUT_DIR / "combined_scan.json"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"{MODEL_DIR} not found — run download_model.py first"
        )

    print("running combined scan ...")

    # modelscan — full directory scan
    modelscan_payload = run_modelscan(MODEL_DIR)

    # fickling — deep dive on the pickle inside pytorch_model.bin
    pickled = load_pytorch_bin_pickle(BIN_FILE)
    fickling_payload = analyze_pickle(pickled)
    fickling_payload["file"] = str(BIN_FILE)

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
            "scanner_version": "security_scanning_tests-0.1.0",
            "container_image": "testing/security_scanning_tests",
        },
    }

    dump_json(COMBINED_OUT, combined)
    print(f"wrote {COMBINED_OUT}")
    print(f"  severity_tier: {combined['severity_tier']}")
    print(f"  fickling is_likely_safe: {fickling_payload['is_likely_safe']}")


if __name__ == "__main__":
    main()
