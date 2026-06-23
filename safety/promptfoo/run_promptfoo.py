#!/usr/bin/env python3
"""
Promptfoo red-team launcher — merges base config with a named profile.

Usage (inside the Docker container or with promptfoo on PATH):
    python run_promptfoo.py <model-name> [--profile base] [--output-dir output/slug/base]

Profiles are defined in promptfoo_profiles.yaml.  The "base" profile uses
promptfooconfig.base.yaml as-is.  All other profiles append additional_plugins
from the profiles file on top of the base plugin list.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent
BASE_CONFIG = CONFIG_DIR / "promptfooconfig.base.yaml"
PROFILES_FILE = CONFIG_DIR / "promptfoo_profiles.yaml"

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

    with BASE_CONFIG.open() as f:
        cfg = yaml.safe_load(f)

    if args.profile != "base":
        with PROFILES_FILE.open() as f:
            profiles = yaml.safe_load(f)
        profile_def = profiles.get(args.profile) or {}
        additional = profile_def.get("additional_plugins") or []
        if additional:
            cfg["redteam"]["plugins"].extend(additional)
            print(
                f"[run_promptfoo] profile={args.profile!r} "
                f"added {len(additional)} plugin(s)"
            )

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

    try:
        result = subprocess.run(
            [
                "promptfoo",
                "redteam",
                "run",
                "-c",
                tmp_path.name,
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
