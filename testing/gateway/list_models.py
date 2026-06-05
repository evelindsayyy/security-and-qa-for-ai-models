#!/usr/bin/env python3
"""List LiteLLM model ids from the Duke AI Gateway (GET /v1/models)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Repo root .env (same keys as evaluator + test_gateway)
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def _credentials() -> tuple[str, str]:
    url = (
        os.getenv("DUKE_GATEWAY_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("DUKE_GATEWAY_BASE_URL")
        or "https://litellm.oit.duke.edu/v1"
    )
    key = (
        os.getenv("DUKE_GATEWAY_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DUKE_AI_GATEWAY_API_KEY")
    )
    if not key:
        print(
            "Set DUKE_GATEWAY_KEY or OPENAI_API_KEY in repo-root .env "
            "(see .env.example).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return url, key


def main() -> int:
    p = argparse.ArgumentParser(description="List Duke Gateway model ids.")
    p.add_argument("--json", action="store_true", help="print JSON array")
    args = p.parse_args()

    from openai import OpenAI

    url, key = _credentials()
    client = OpenAI(base_url=url, api_key=key)
    models = sorted(client.models.list().data, key=lambda m: m.id)

    if args.json:
        print(json.dumps([{"id": m.id, "owned_by": m.owned_by} for m in models], indent=2))
        return 0

    print(f"Duke AI Gateway — {len(models)} models ({url})")
    print()
    for m in models:
        print(m.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
