"""
load_benchmarks.py — benchmark result files -> public.benchmark_runs.

Reads ``*.json`` and ``*.jsonl`` under ``benchmarks/results/`` and loads
parsed rows into Postgres. Uses shared ``dbutils`` for env, file IO, connect,
JSONB params, and the dry-run CLI contract.

SAFE BY DEFAULT: without ``--apply`` this is a dry run.

Idempotent: re-running with ``--apply`` uses ON CONFLICT (output_slug) DO NOTHING.

Run from repo root:
    uv run python benchmarks/db/load_benchmarks.py                 # dry run
    uv run python benchmarks/db/load_benchmarks.py --apply         # real load
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

from benchmarks.db.transforms import benchmark_run_row
from dbutils import apply_loader, jsonb_param, load_repo_env
from dbutils.cli import add_ingest_arguments
from dbutils.ingest import exit_if_apply_without_dsn, print_dry_run_hint

BENCHMARKS = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BENCHMARKS / "results"


@dataclass
class IngestResult:
    count: int
    label: str = "benchmark run(s)"


def iter_result_files(output_dir: Path) -> list[Path]:
    if not output_dir.is_dir():
        return []
    paths = sorted(output_dir.glob("*.json")) + sorted(output_dir.glob("*.jsonl"))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        if path.suffix == ".log" or path.stem in seen:
            continue
        seen.add(path.stem)
        unique.append(path)
    return unique


def load_file(path: Path) -> dict[str, Any] | None:
    return benchmark_run_row(path)


def load_into(conn, parsed: list[dict[str, Any]]) -> None:
    """All cursor work + one commit."""
    _INSERT = """
INSERT INTO public.benchmark_runs (
    model_id, output_slug, source_filename, gateway_model_id, benchmark_key,
    inference_backend, status, headline_metric, headline_value, n_items,
    metrics, items, run_params, started_at, completed_at)
VALUES (
    %(model_id)s, %(output_slug)s, %(source_filename)s, %(gateway_model_id)s,
    %(benchmark_key)s, %(inference_backend)s, %(status)s, %(headline_metric)s,
    %(headline_value)s, %(n_items)s, %(metrics)s::jsonb, %(items)s::jsonb,
    %(run_params)s::jsonb, %(started_at)s, %(completed_at)s)
ON CONFLICT (output_slug) DO NOTHING
"""
    with conn.cursor() as cur:
        for row in parsed:
            params = {
                **row,
                "metrics": jsonb_param(row["metrics"]),
                "items": jsonb_param(row["items"]),
                "run_params": jsonb_param(row["run_params"])
                if row.get("run_params") is not None
                else None,
            }
            cur.execute(_INSERT, params)
    conn.commit()


def sync_file(path: Path, *, dsn: str) -> None:
    """Load one benchmark result file into Postgres (idempotent)."""
    parsed = load_file(path)
    if parsed is None:
        raise ValueError(f"could not parse {path.name}")
    apply_loader(
        dsn,
        lambda conn: load_into(conn, [parsed]),
        item_count=1,
        item_label="benchmark run(s)",
        quiet=True,
    )


def run_ingest(
    *,
    apply: bool,
    dsn: str | None,
    output_dir: Path | None = None,
) -> IngestResult:
    """Collect and optionally load benchmark runs. Used by CLI and api.ingest."""
    root = output_dir or OUTPUT_DIR
    paths = iter_result_files(root)
    parsed = [r for r in (load_file(p) for p in paths) if r is not None]

    print(f"{len(parsed)} loadable benchmark run(s) in {root}:")
    for row in parsed:
        hv = row["headline_value"]
        hv_s = f"{hv:.4f}" if hv is not None else "—"
        print(
            f"  {row['output_slug']}:  {row['benchmark_key']}  "
            f"model={row['gateway_model_id']}  {row['headline_metric']}={hv_s}  "
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
        item_label="benchmark run(s)",
    )
    return IngestResult(count=len(parsed))


def main() -> int:
    load_repo_env()
    ap = argparse.ArgumentParser(
        description="Load benchmark result files into Postgres."
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="benchmark results root (default: benchmarks/results)",
    )
    add_ingest_arguments(ap)
    args = ap.parse_args()
    run_ingest(apply=args.apply, dsn=args.dsn, output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
