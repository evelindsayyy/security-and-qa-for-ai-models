#!/usr/bin/env python3
"""Export Garak report JSONL → ``safety_result.json``. Logic: ``safety.exporters.garak``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from safety.exporters.garak import export_from_garak_report

DEFAULT_OUTPUT = "safety_result.json"
DEFAULT_REPORT_GLOB = "garak-gpt41mini-low-guardrail.report.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Garak JSONL to SafetyRunResult JSON.")
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=Path(f"output/{DEFAULT_REPORT_GLOB}"),
        help=f"Report JSONL (default: output/{DEFAULT_REPORT_GLOB})",
    )
    parser.add_argument("-o", "--output", type=Path, help=f"Default: output/{DEFAULT_OUTPUT}")
    parser.add_argument("--probe-suite", default="garak_subset_v1")
    args = parser.parse_args()

    try:
        doc = export_from_garak_report(args.input, probe_suite=args.probe_suite)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out = args.output or (args.input.parent / DEFAULT_OUTPUT)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {out}")
    print(
        f"  gateway_model_id={doc['gateway_model_id']}  "
        f"pass_rate={doc['summary_pass_rate']:.0%}  findings={len(doc['findings'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
