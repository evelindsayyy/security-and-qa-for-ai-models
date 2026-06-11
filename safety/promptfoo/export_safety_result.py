#!/usr/bin/env python3
"""
Export Promptfoo eval JSON → ``SafetyRunResult`` JSON.

Thin CLI wrapper — logic lives in ``safety.exporters.promptfoo``.
Auto-names output: policy → safety_result.json, red-team → redteam_safety_result.json.

Run from repo root (needs PYTHONPATH):
    PYTHONPATH=. uv run python safety/promptfoo/export_safety_result.py \\
      safety/promptfoo/output/<slug>/eval.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from safety.exporters.promptfoo import (
    SUITE_POLICY,
    SUITE_REDTEAM,
    detect_promptfoo_suite,
    export_from_promptfoo_eval,
)

DEFAULT_POLICY_OUTPUT = "safety_result.json"
DEFAULT_REDTEAM_OUTPUT = "redteam_safety_result.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Promptfoo eval to SafetyRunResult JSON.")
    parser.add_argument("input", type=Path, help="Raw eval JSON (eval.json or redteam_eval.json)")
    parser.add_argument("-o", "--output", type=Path, help="Output path (auto-named if omitted)")
    parser.add_argument(
        "--probe-suite",
        default=None,
        help=f"Override suite (default: auto — {SUITE_POLICY} or {SUITE_REDTEAM})",
    )
    parser.add_argument(
        "--redteam",
        action="store_true",
        help=f"Force {SUITE_REDTEAM} (same as auto-detect on redteam_eval.json)",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"ERROR: file not found: {args.input}", file=sys.stderr)
        return 1

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    suite = args.probe_suite or (SUITE_REDTEAM if args.redteam else None) or detect_promptfoo_suite(payload)

    if args.output:
        out = args.output
    elif suite == SUITE_REDTEAM:
        out = args.input.parent / DEFAULT_REDTEAM_OUTPUT
    else:
        out = args.input.parent / DEFAULT_POLICY_OUTPUT

    doc = export_from_promptfoo_eval(
        payload,
        source_file=str(args.input),
        probe_suite=suite,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {out}")
    print(
        f"  probe_suite={doc['probe_suite']}  "
        f"gateway_model_id={doc['gateway_model_id']}  "
        f"pass_rate={doc['summary_pass_rate']:.0%}  findings={len(doc['findings'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
