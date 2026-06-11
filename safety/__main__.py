#!/usr/bin/env python3
"""CLI entry point for the safety red-teaming pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from safety.pipeline import scan_model


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m safety",
        description="Run Promptfoo/Garak red-team scans for a target model.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Run the full safety pipeline for a model")
    scan_parser.add_argument("model_id", help="Model or provider alias to evaluate")
    scan_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output directory for the combined safety result",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        result = scan_model(args.model_id, output_dir=args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
