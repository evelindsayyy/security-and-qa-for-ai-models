"""
run modelscan against the downloaded model directory.

run inside the container:
    python run_modelscan.py

writes to /output/ (bind-mounted to ./output/ on dgx):
    modelscan_report.json  — structured output (what our scanner will parse)
    modelscan_report.txt   — plain-text summary (no emojis)
"""

from pathlib import Path

from scan_helpers import dump_json, format_modelscan_text, run_modelscan

# where download_model.py put the files
MODEL_DIR = Path("/models/distilbert-base-uncased")

# bind-mounted output folder on dgx — note: /output inside container, not ./output
OUTPUT_DIR = Path("/output")
JSON_OUT = OUTPUT_DIR / "modelscan_report.json"
TEXT_OUT = OUTPUT_DIR / "modelscan_report.txt"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"{MODEL_DIR} not found — run download_model.py first"
        )

    print(f"running modelscan on {MODEL_DIR} ...")

    # use python api — newer modelscan dropped --output-format cli flag
    payload = run_modelscan(MODEL_DIR)

    dump_json(JSON_OUT, payload)
    print(f"wrote {JSON_OUT}")

    TEXT_OUT.write_text(format_modelscan_text(payload))
    print(f"wrote {TEXT_OUT}")

    # quick terminal summary
    summary = payload.get("summary", {})
    print("\nmodelscan summary:")
    print(f"  total issues: {summary.get('total_issues', 0)}")
    print(f"  severity counts: {summary.get('total_issues_by_severity', {})}")


if __name__ == "__main__":
    main()
