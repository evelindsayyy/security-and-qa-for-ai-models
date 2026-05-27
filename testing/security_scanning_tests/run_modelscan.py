"""run modelscan on /models/distilbert-base-uncased — writes json + txt to /output/."""

from pathlib import Path

from scan_helpers import dump_json, format_modelscan_text, run_modelscan

MODEL_DIR = Path("/models/distilbert-base-uncased")
OUTPUT_DIR = Path("/output")


def main() -> None:
    if not MODEL_DIR.exists():
        raise FileNotFoundError(f"{MODEL_DIR} not found — run download_model.py first")

    print(f"running modelscan on {MODEL_DIR} ...")
    payload = run_modelscan(MODEL_DIR)

    dump_json(OUTPUT_DIR / "modelscan_report.json", payload)
    (OUTPUT_DIR / "modelscan_report.txt").write_text(format_modelscan_text(payload))

    summary = payload.get("summary", {})
    print(f"wrote /output/modelscan_report.json")
    print(f"  total issues: {summary.get('total_issues', 0)}")


if __name__ == "__main__":
    main()
