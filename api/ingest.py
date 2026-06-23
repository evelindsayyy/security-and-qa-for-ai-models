"""
api.ingest — unified Postgres ingest for scan, safety, eval, and benchmark pillars.

Dry-run by default. Each pillar loader prints what it would load;
``--apply`` writes to Postgres when a DSN is set.

Run from repo root:
    uv run python -m api.ingest                    # dry-run all four pillars
    uv run python -m api.ingest --apply            # load all (needs DSN)
    uv run python -m api.ingest --scan             # single pillar
    uv run python -m api.ingest bootstrap --apply  # all pillars + seed summary
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from dbutils import load_repo_env, resolve_dsn

PILLARS = ("scan", "safety", "eval", "benchmark")


@dataclass
class PillarResult:
    name: str
    count: int
    label: str


def _run_scan(*, apply: bool, dsn: str | None, output_dir: Path | None) -> PillarResult:
    from scanner.db.load_scans import run_ingest

    r = run_ingest(apply=apply, dsn=dsn, output_dir=output_dir)
    return PillarResult("scan", r.count, r.label)


def _run_safety(*, apply: bool, dsn: str | None, output_dir: Path | None) -> PillarResult:
    from safety.db.load_safety import run_ingest

    r = run_ingest(apply=apply, dsn=dsn, output_dir=output_dir)
    return PillarResult("safety", r.count, r.label)


def _run_eval(*, apply: bool, dsn: str | None, results_dir: Path | None) -> PillarResult:
    from evaluator.db.load_results import run_ingest

    r = run_ingest(apply=apply, dsn=dsn, results_dir=results_dir)
    return PillarResult("eval", r.count, r.label)


def _run_benchmark(*, apply: bool, dsn: str | None, output_dir: Path | None) -> PillarResult:
    from benchmarks.db.load_benchmarks import run_ingest

    r = run_ingest(apply=apply, dsn=dsn, output_dir=output_dir)
    return PillarResult("benchmark", r.count, r.label)


_PILLAR_RUNNERS: dict[str, Callable[..., PillarResult]] = {
    "scan": _run_scan,
    "safety": _run_safety,
    "eval": _run_eval,
    "benchmark": _run_benchmark,
}


def run_ingest_all(
    *,
    pillars: tuple[str, ...],
    apply: bool,
    dsn: str | None,
    scan_dir: Path | None = None,
    safety_dir: Path | None = None,
    eval_dir: Path | None = None,
    benchmark_dir: Path | None = None,
) -> list[PillarResult]:
    """Run selected pillar ingest functions and return per-pillar counts."""
    dirs = {
        "scan": scan_dir,
        "safety": safety_dir,
        "eval": eval_dir,
        "benchmark": benchmark_dir,
    }
    results: list[PillarResult] = []
    for name in pillars:
        runner = _PILLAR_RUNNERS[name]
        if name == "eval":
            results.append(runner(apply=apply, dsn=dsn, results_dir=dirs[name]))
        else:
            results.append(runner(apply=apply, dsn=dsn, output_dir=dirs[name]))
    return results


def _print_summary(results: list[PillarResult], *, bootstrap: bool) -> None:
    parts = ", ".join(f"{r.name}={r.count}" for r in results)
    if bootstrap:
        print(f"Seed complete: {parts}")
    else:
        print(f"Ingest summary: {parts}")


def main(argv: list[str] | None = None) -> int:
    load_repo_env()

    ap = argparse.ArgumentParser(
        description="Unified Postgres ingest for scan, safety, eval, and benchmark pillars."
    )
    ap.add_argument(
        "command",
        nargs="?",
        choices=("bootstrap",),
        help="bootstrap: run all pillars and print a one-line seed summary",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write to Postgres (default: dry run, no database connection)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero if any selected pillar has zero loadable files",
    )
    ap.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN (or set POSTGRES_DSN / DATABASE_URL / EFFICACY_DB_DSN)",
    )
    ap.add_argument("--scan", action="store_true", help="ingest scanner output only")
    ap.add_argument("--safety", action="store_true", help="ingest safety output only")
    ap.add_argument("--eval", action="store_true", help="ingest evaluator results only")
    ap.add_argument(
        "--benchmark", action="store_true", help="ingest benchmark results only"
    )
    ap.add_argument("--scan-output-dir", type=Path, default=None)
    ap.add_argument("--safety-output-dir", type=Path, default=None)
    ap.add_argument("--eval-results-dir", type=Path, default=None)
    ap.add_argument("--benchmark-output-dir", type=Path, default=None)
    args = ap.parse_args(argv)

    selected = tuple(p for p in PILLARS if getattr(args, p))
    if not selected:
        selected = PILLARS

    dsn = args.dsn or resolve_dsn("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")

    print(f"Running ingest ({'apply' if args.apply else 'dry-run'}) for: {', '.join(selected)}")
    results = run_ingest_all(
        pillars=selected,
        apply=args.apply,
        dsn=dsn,
        scan_dir=args.scan_output_dir,
        safety_dir=args.safety_output_dir,
        eval_dir=args.eval_results_dir,
        benchmark_dir=args.benchmark_output_dir,
    )
    _print_summary(results, bootstrap=args.command == "bootstrap")

    if args.strict and any(r.count == 0 for r in results):
        print("Strict mode: one or more pillars had zero loadable files.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
