#!/usr/bin/env python3
"""CLI entry point for the safety red-teaming pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from safety.pipeline import scan_model
from safety.safety_score import PASS_THRESHOLDS, score_garak_file, score_promptfoo_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m safety",
        description="Run Promptfoo/Garak red-team scans for a target model.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Run Garak and Promptfoo and write separate Track A safety results",
    )
    scan_parser.add_argument("model_id", help="Model or provider alias to evaluate")
    scan_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output root for tool-specific safety results",
    )

    garak_parser = subparsers.add_parser("score-garak", help="Score an existing Garak report")
    garak_parser.add_argument("--input", required=True, type=Path)
    garak_parser.add_argument("--output", required=True, type=Path)
    garak_parser.add_argument("--model-id")
    garak_parser.add_argument(
        "--deployment-context-json",
        help="JSON object copied into safety_runs.deployment_context",
    )
    garak_parser.add_argument(
        "--default-severity",
        choices=sorted(PASS_THRESHOLDS),
        default="high",
    )

    promptfoo_parser = subparsers.add_parser(
        "score-promptfoo",
        help="Score an existing Promptfoo report",
    )
    promptfoo_parser.add_argument("--input", required=True, type=Path)
    promptfoo_parser.add_argument("--output", required=True, type=Path)
    promptfoo_parser.add_argument("--model-id")
    promptfoo_parser.add_argument(
        "--deployment-context-json",
        help="JSON object copied into safety_runs.deployment_context",
    )
    promptfoo_parser.add_argument(
        "--default-severity",
        choices=sorted(PASS_THRESHOLDS),
        default="medium",
    )
    return parser


def _deployment_context(value: str | None) -> dict | None:
    if not value:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise SystemExit("--deployment-context-json must decode to a JSON object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        result = scan_model(args.model_id, output_dir=args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "score-garak":
        result = score_garak_file(
            args.input,
            args.output,
            model_id=args.model_id,
            deployment_context=_deployment_context(args.deployment_context_json),
            default_severity=args.default_severity,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "score-promptfoo":
        result = score_promptfoo_file(
            args.input,
            args.output,
            model_id=args.model_id,
            deployment_context=_deployment_context(args.deployment_context_json),
            default_severity=args.default_severity,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
