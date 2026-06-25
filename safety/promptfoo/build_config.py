#!/usr/bin/env python3
"""
Build a merged Promptfoo red-team YAML for a named profile.

Writes ``redteam_promptfooconfig.yaml`` under *output_dir* so the orchestrator
and nested Promptfoo container share the same bind-mounted path.

Usage (from repo root):
    PYTHONPATH=. uv run python safety/promptfoo/build_config.py \\
      --profile healthcare --output-dir safety/promptfoo/output/gpt-4.1-mini/base
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent
BASE_CONFIG = CONFIG_DIR / "promptfooconfig.base.yaml"
PROFILES_FILE = CONFIG_DIR / "promptfoo_profiles.yaml"
OUTPUT_NAME = "redteam_promptfooconfig.yaml"

PROFILES = frozenset({"base", "education", "healthcare", "finance", "rag", "agentic"})


def merge_redteam_config(profile: str) -> dict:
    """Return merged red-team config dict for *profile*."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; valid: {sorted(PROFILES)}")

    with BASE_CONFIG.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if profile != "base":
        with PROFILES_FILE.open(encoding="utf-8") as f:
            profiles = yaml.safe_load(f)
        profile_def = profiles.get(profile) or {}
        additional = profile_def.get("additional_plugins") or []
        if additional:
            cfg["redteam"]["plugins"].extend(additional)

    return cfg


def write_redteam_config(profile: str, output_dir: Path) -> Path:
    """Write merged config under *output_dir*; return absolute path."""
    cfg = merge_redteam_config(profile)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / OUTPUT_NAME
    out.write_text(
        yaml.dump(cfg, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    return out.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Promptfoo red-team config for a profile.")
    parser.add_argument("--profile", default="base")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    try:
        path = write_redteam_config(args.profile, args.output_dir)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
