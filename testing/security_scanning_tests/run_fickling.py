"""
analyze the pickle-based pytorch weights file with fickling.

run inside the container:
    python run_fickling.py

writes:
    /output/fickling_report.json  (bind-mounted to ./output/ on dgx)
"""

import json
from pathlib import Path

import fickling

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

    with BIN_FILE.open("rb") as handle:
        # load the pickle AST without executing arbitrary code
        pickled = fickling.Pickled.load(handle)

    # high-level yes/no — distilbert should be True (legit model)
    likely_safe = fickling.is_likely_safe(pickled)

    # count what kinds of AST nodes show up — useful for documenting fickling output
    node_types: dict[str, int] = {}
    for node in pickled.ast.body:
        name = type(node).__name__
        node_types[name] = node_types.get(name, 0) + 1

    report = {
        "file": str(BIN_FILE),
        "is_likely_safe": likely_safe,
        "ast_node_count": len(pickled.ast.body),
        "ast_node_types": node_types,
    }

    JSON_OUT.write_text(json.dumps(report, indent=2))
    print(f"wrote {JSON_OUT}")
    print("\nfickling summary:")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
