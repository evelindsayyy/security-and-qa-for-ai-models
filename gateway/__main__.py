"""
CLI for the live Duke AI Gateway catalog.

    uv run python -m gateway            # human-readable, grouped by category
    uv run python -m gateway --json     # JSON array (seed / import)
    uv run python -m gateway --ids      # one id per line (scripting)

Same source the frontend dropdowns and /models page use.
"""

from __future__ import annotations

import argparse
import json
import sys

from gateway.catalog import get_gateway_catalog


def main() -> int:
    p = argparse.ArgumentParser(description="List Duke AI Gateway model ids.")
    p.add_argument("--json", action="store_true", help="print JSON array")
    p.add_argument("--ids", action="store_true", help="print one id per line")
    args = p.parse_args()

    gw = get_gateway_catalog(force_refresh=True)
    if gw["error"]:
        print(gw["error"], file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(gw["models"], indent=2))
        return 0

    if args.ids:
        for m in gw["models"]:
            print(m["id"])
        return 0

    print(f"Duke AI Gateway — {gw['count']} models ({gw['source']})\n")
    for section in gw["by_category"]:
        print(f"## {section['label']}")
        for m in section["models"]:
            note = f"  — {m['notes']}" if m["notes"] else ""
            print(f"  {m['id']}{note}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
