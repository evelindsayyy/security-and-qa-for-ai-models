#!/usr/bin/env python3
"""
Export Garak report JSONL → ``safety_result.json``.

Thin CLI wrapper — logic lives in ``safety.exporters.garak``.
Default report glob matches ``garak-duke-*.report.jsonl`` under output/<slug>/.

Run from repo root (needs PYTHONPATH):
    PYTHONPATH=. uv run python safety/garak/export_safety_result.py \\
      safety/garak/output/<slug>/garak-duke-*.report.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from safety.exporters.garak import export_from_garak_report

DEFAULT_OUTPUT = "safety_result.json"
DEFAULT_REPORT_GLOB = "garak-duke-*.report.jsonl"


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
    parser.add_argument("--gateway-model-id", default=None, help="Override target model slug source")
    args = parser.parse_args()

    try:
        doc = export_from_garak_report(
            args.input,
            probe_suite=args.probe_suite,
            gateway_model_id=args.gateway_model_id,
        )
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
