"""
run modelscan against the downloaded model directory.

run inside the container:
    python run_modelscan.py

writes to /output/ (bind-mounted to ./output/ on dgx):
    modelscan_report.json  — structured output (what our scanner will parse)
    modelscan_report.txt   — human-readable log for docs / debugging
"""

import json
import subprocess
from pathlib import Path

# where download_model.py put the files
MODEL_DIR = Path("/models/distilbert-base-uncased")

# bind-mounted output folder on dgx
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

    # --- json report (the important one for our scanner schema) ---
    json_result = subprocess.run(
        ["modelscan", "scan", "-p", str(MODEL_DIR), "--output-format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )

    # modelscan sometimes prints warnings to stderr even on success
    json_body = json_result.stdout or json_result.stderr
    JSON_OUT.write_text(json_body)
    print(f"wrote {JSON_OUT}")

    # --- plain text report (nice to read in terminal / paste into notes) ---
    text_result = subprocess.run(
        ["modelscan", "scan", "-p", str(MODEL_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    text_body = text_result.stdout or text_result.stderr
    TEXT_OUT.write_text(text_body)
    print(f"wrote {TEXT_OUT}")

    # print a quick summary so you don't have to open the json file immediately
    if json_result.stdout:
        try:
            payload = json.loads(json_result.stdout)
            summary = payload.get("summary", {})
            print("\nmodelscan summary:")
            print(json.dumps(summary, indent=2))
        except json.JSONDecodeError:
            print("(couldn't parse json stdout — check modelscan_report.json manually)")


if __name__ == "__main__":
    main()
