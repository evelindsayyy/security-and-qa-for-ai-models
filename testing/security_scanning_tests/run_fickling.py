"""run fickling on pytorch_model.bin — writes json to /output/."""

from pathlib import Path

from scan_helpers import analyze_pytorch_bin, dump_json

BIN_FILE = Path("/models/distilbert-base-uncased/pytorch_model.bin")
OUTPUT_DIR = Path("/output")


def main() -> None:
    if not BIN_FILE.exists():
        raise FileNotFoundError(f"{BIN_FILE} not found — run download_model.py first")

    print(f"running fickling on {BIN_FILE} ...")
    report = analyze_pytorch_bin(BIN_FILE)
    dump_json(OUTPUT_DIR / "fickling_report.json", report)

    print("wrote /output/fickling_report.json")
    print(f"  format: {report['pytorch_format']}, safe: {report['is_likely_safe']}")


if __name__ == "__main__":
    main()
