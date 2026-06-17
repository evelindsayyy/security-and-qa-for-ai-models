"""
smoke test: load gpt2 combined_scan.json into pydantic ScanResult.

run inside container after a scan:
  python schemas_demo.py

expects /output/gpt2/combined_scan.json (or MODEL_ID env for other models).
"""

import json
import sys

from scan_helpers import get_model_id, output_dir
from schemas import ScanResult, build_scan_result_from_combined


def main() -> None:
    model_id = get_model_id()
    path = output_dir(model_id) / "combined_scan.json"

    if not path.is_file():
        print(f"missing {path} — run run_combined_scan.py first", file=sys.stderr)
        sys.exit(1)

    combined = json.loads(path.read_text())
    result = build_scan_result_from_combined(combined)

    # pydantic v2 validation round-trip
    validated = ScanResult.model_validate(result.model_dump())

    print(f"model_id: {validated.model_id}")
    print(f"severity_tier: {validated.severity_tier}")
    print(f"findings count: {len(validated.findings)}")
    print(f"fickling_severity (spike field): {validated.fickling_severity}")
    for f in validated.findings:
        print(f"  - [{f.source}] {f.title} ({f.severity}, raw={f.raw_tool_severity})")

    print("\nvalidated ScanResult JSON (truncated tool_results):")
    dump = validated.model_dump()
    dump["tool_results"] = {"...": "see combined_scan.json"}
    print(json.dumps(dump, indent=2, default=str))


if __name__ == "__main__":
    main()
