#!/usr/bin/env python3
"""
Merge per-tool ``safety_result.json`` files → ``merged_safety_result.json``.

Usage (repo root):
    uv run python -m safety.merge \
      --promptfoo safety/promptfoo/output/safety_result.json \
      --garak safety/garak/output/safety_result.json \
      -o safety/output/gpt-4.1-mini/merged_safety_result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from safety.safety_scorer import merge_safety_runs
from safety.schemas import SafetyRunResult


def _load_run(path: Path) -> SafetyRunResult:
    return SafetyRunResult.model_validate(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge SafetyRunResult JSON files.")
    parser.add_argument("--promptfoo", type=Path, action="append", default=[])
    parser.add_argument("--garak", type=Path, action="append", default=[])
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()

    paths = list(args.promptfoo) + list(args.garak) + list(args.inputs)
    if not paths:
        print("ERROR: pass --promptfoo, --garak, or positional paths", file=sys.stderr)
        return 1

    runs = []
    for p in paths:
        if not p.is_file():
            print(f"ERROR: file not found: {p}", file=sys.stderr)
            return 1
        runs.append(_load_run(p))

    try:
        merged = merge_safety_runs(runs)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(merged.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Wrote {args.output}")
    print(
        f"  gateway_model_id={merged.gateway_model_id}  "
        f"pass_rate={merged.summary_pass_rate:.0%}  "
        f"safety_tier={merged.safety_tier.value}  "
        f"findings={len(merged.findings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
