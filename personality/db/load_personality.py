"""
load_personality.py — personality result files -> public.personality_runs.

Reads ``*.json`` under ``personality/results/`` and loads parsed rows into
Postgres. Uses shared ``dbutils`` for env, connect, JSONB params, and the
dry-run CLI contract.

SAFE BY DEFAULT: without ``--apply`` this is a dry run.

Idempotent: re-running with ``--apply`` uses ON CONFLICT (output_slug) DO NOTHING.

Run from repo root:
    uv run python personality/db/load_personality.py                 # dry run
    uv run python personality/db/load_personality.py --apply         # real load
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dbutils import apply_loader, jsonb_param, load_repo_env
from dbutils.auth_columns import apply_auth_defaults, auth_fields_from_artifact
from dbutils.cli import add_ingest_arguments
from dbutils.ingest import exit_if_apply_without_dsn, print_dry_run_hint
from personality.db.transforms import personality_run_row

PERSONALITY = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PERSONALITY / "results"


@dataclass
class IngestResult:
    count: int
    label: str = "personality run(s)"


def iter_result_files(output_dir: Path) -> list[Path]:
    if not output_dir.is_dir():
        return []
    paths = sorted(output_dir.glob("*.json"))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        if path.stem.endswith(".progress") or path.stem in seen:
            continue
        seen.add(path.stem)
        unique.append(path)
    return unique


def load_file(path: Path) -> dict[str, Any] | None:
    row = personality_run_row(path)
    if row is None:
        return None
    apply_auth_defaults(row, auth_fields_from_artifact(path, pillar="personality"))
    return row


def load_into(conn, parsed: list[dict[str, Any]]) -> None:
    """All cursor work + one commit."""
    _INSERT = """
INSERT INTO public.personality_runs (
    output_slug, source_filename, gateway_model_id, test_key, status,
    n_items, attempted, scored, coverage, traits, items, summary,
    started_at, completed_at,
    visibility, owner_user_id, config_fingerprint, config_json)
VALUES (
    %(output_slug)s, %(source_filename)s, %(gateway_model_id)s, %(test_key)s,
    %(status)s, %(n_items)s, %(attempted)s, %(scored)s, %(coverage)s,
    %(traits)s::jsonb, %(items)s::jsonb, %(summary)s::jsonb,
    %(started_at)s, %(completed_at)s,
    %(visibility)s, %(owner_user_id)s, %(config_fingerprint)s, %(config_json)s::jsonb)
ON CONFLICT (output_slug) DO NOTHING
"""
    with conn.cursor() as cur:
        for row in parsed:
            params = {
                **row,
                "traits": jsonb_param(row["traits"]),
                "items": jsonb_param(row["items"]),
                "summary": jsonb_param(row["summary"]),
                "config_json": jsonb_param(row.get("config_json") or {}),
            }
            cur.execute(_INSERT, params)
    conn.commit()


def sync_file(path: Path, *, dsn: str) -> None:
    """Load one personality result file into Postgres (idempotent)."""
    parsed = load_file(path)
    if parsed is None:
        raise ValueError(f"could not parse {path.name}")
    apply_loader(
        dsn,
        lambda conn: load_into(conn, [parsed]),
        item_count=1,
        item_label="personality run(s)",
        quiet=True,
    )


def run_ingest(
    *,
    apply: bool,
    dsn: str | None,
    output_dir: Path | None = None,
) -> IngestResult:
    """Collect and optionally load personality runs. Used by CLI and api.ingest."""
    root = output_dir or OUTPUT_DIR
    paths = iter_result_files(root)
    parsed = [r for r in (load_file(p) for p in paths) if r is not None]

    print(f"{len(parsed)} loadable personality run(s) in {root}:")
    for row in parsed:
        cov = row.get("coverage")
        cov_s = f"{cov:.0%}" if cov is not None else "—"
        print(
            f"  {row['output_slug']}:  {row['test_key']}  "
            f"model={row['gateway_model_id']}  coverage={cov_s}  "
            f"n={row['n_items']}"
        )

    if not apply:
        print_dry_run_hint()
        return IngestResult(count=len(parsed))

    exit_if_apply_without_dsn(dsn)
    apply_loader(
        dsn,
        lambda conn: load_into(conn, parsed),
        item_count=len(parsed),
        item_label="personality run(s)",
    )
    return IngestResult(count=len(parsed))


def main() -> int:
    load_repo_env()
    ap = argparse.ArgumentParser(
        description="Load personality result files into Postgres."
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="personality results root (default: personality/results)",
    )
    add_ingest_arguments(ap)
    args = ap.parse_args()
    run_ingest(apply=args.apply, dsn=args.dsn, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
