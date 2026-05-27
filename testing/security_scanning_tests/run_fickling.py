"""
analyze the pickle inside pytorch_model.bin with fickling.

run inside the container:
    python run_fickling.py

why not point fickling at the .bin directly?
    pytorch .bin is a zip archive — we extract archive/data.pkl first
    (see scan_helpers.load_pytorch_bin_pickle)

writes:
    /output/fickling_report.json  (bind-mounted to ./output/ on dgx)
"""

from pathlib import Path

from scan_helpers import analyze_pickle, dump_json, load_pytorch_bin_pickle

MODEL_DIR = Path("/models/distilbert-base-uncased")
BIN_FILE = MODEL_DIR / "pytorch_model.bin"
OUTPUT_DIR = Path("/output")
JSON_OUT = OUTPUT_DIR / "fickling_report.json"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not BIN_FILE.exists():
        raise FileNotFoundError(
            f"{BIN_FILE} not found — run download_model.py first"
        )

    print(f"running fickling on {BIN_FILE} ...")

    # pull pickle out of the pytorch zip wrapper, then analyze
    pickled = load_pytorch_bin_pickle(BIN_FILE)
    report = analyze_pickle(pickled)
    report["file"] = str(BIN_FILE)

    dump_json(JSON_OUT, report)
    print(f"wrote {JSON_OUT}")
    print("\nfickling summary:")
    print(f"  is_likely_safe: {report['is_likely_safe']}")
    print(f"  severity: {report['severity']}")
    print(f"  ast_node_count: {report['ast_node_count']}")


if __name__ == "__main__":
    main()
