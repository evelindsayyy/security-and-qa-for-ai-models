"""merge modelscan + fickling into one json — see docs/scanner-output-format.md."""

from datetime import datetime, timezone
from pathlib import Path

from scan_helpers import analyze_pytorch_bin, dump_json, run_modelscan, severity_tier

MODEL_ID = "distilbert-base-uncased"
MODEL_DIR = Path("/models") / MODEL_ID
BIN_FILE = MODEL_DIR / "pytorch_model.bin"


def main() -> None:
    if not MODEL_DIR.exists():
        raise FileNotFoundError(f"{MODEL_DIR} not found — run download_model.py first")

    print("running combined scan ...")
    modelscan = run_modelscan(MODEL_DIR)
    fickling = analyze_pytorch_bin(BIN_FILE)

    combined = {
        "model_id": MODEL_ID,
        "scanned_files": ["pytorch_model.bin", "model.safetensors"],
        "overall_risk_score": 0,
        "severity_tier": severity_tier(modelscan),
        "findings": modelscan.get("issues", []),
        "tool_results": {
            "modelscan": modelscan.get("summary", modelscan),
            "fickling": fickling,
        },
        "scan_metadata": {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "scanner_version": "security_scanning_tests-0.1.0",
        },
    }

    dump_json(Path("/output/combined_scan.json"), combined)
    print("wrote /output/combined_scan.json")
    print(f"  tier: {combined['severity_tier']}, fickling safe: {fickling['is_likely_safe']}")


if __name__ == "__main__":
    main()
