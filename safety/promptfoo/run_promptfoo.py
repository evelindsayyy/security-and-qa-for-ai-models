#!/usr/bin/env python3
"""
Promptfoo red-team launcher — merges base config with a named profile.

Usage (inside the Docker container or with promptfoo on PATH):
    python run_promptfoo.py <model-name> [--profile base] [--output-dir output/slug/base]

Profiles are defined in promptfoo_profiles.yaml.  Prefer orchestrator-side
``build_config.py`` + ``promptfoo redteam run`` from ``safety.run``; this script
remains for manual CLI use.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

try:
    from safety.promptfoo.build_config import merge_redteam_config
except ImportError:
    from build_config import merge_redteam_config

CONFIG_DIR = Path(__file__).parent
PROFILES = {"base", "education", "healthcare", "finance", "rag", "agentic"}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("model_name")
    parser.add_argument("--profile", default="base")
    parser.add_argument("--output-dir", default=None)
    args, extra_args = parser.parse_known_args()

    if args.profile not in PROFILES:
        print(
            f"[run_promptfoo] unknown profile {args.profile!r}; "
            f"valid: {sorted(PROFILES)}",
            file=sys.stderr,
        )
        return 1

    try:
        cfg = merge_redteam_config(args.profile)
    except ValueError as exc:
        print(f"[run_promptfoo] {exc}", file=sys.stderr)
        return 1

    output_dir = args.output_dir or f"output/{args.model_name}/{args.profile}"
    output_file = f"{output_dir}/redteam_eval.json"

    print(
        f"[run_promptfoo] model={args.model_name!r}  "
        f"profile={args.profile!r}  output={output_file}"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", dir=CONFIG_DIR, delete=False
    ) as tmp:
        yaml.dump(cfg, tmp, default_flow_style=False, allow_unicode=True)
        tmp_path = Path(tmp.name)

    config_path = str(tmp_path.resolve())
    try:
        result = subprocess.run(
            [
                "promptfoo",
                "redteam",
                "run",
                "-c",
                config_path,
                "-o",
                output_file,
                "--delay",
                "500",
                "--max-concurrency",
                "1",
                "--force",
                *extra_args,
            ],
            check=False,
        )
        return result.returncode
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
