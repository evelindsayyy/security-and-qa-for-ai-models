#!/usr/bin/env python3
"""Backfill auth columns on existing pillar run rows."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dbutils.env import load_repo_env, resolve_dsn  # noqa: E402
from dbutils.ingest import jsonb_param  # noqa: E402
from dbutils.run_fingerprint import (  # noqa: E402
    fingerprint,
    is_public_default,
    normalize_benchmark_config,
    normalize_eval_config,
    normalize_safety_config,
    normalize_scan_config,
)

load_repo_env()


def _existing_fingerprints(cur, table: str) -> set[str]:
    """Fingerprints already stored (e.g. from a prior partial migration)."""
    cur.execute(
        f"""
        SELECT config_fingerprint FROM public.{table}
        WHERE config_fingerprint IS NOT NULL
        """
    )
    return {row[0] for row in cur.fetchall()}


def _assign_fingerprint(fp: str, seen: set[str]) -> str | None:
    """Keep one canonical row per fingerprint (partial unique index)."""
    if fp in seen:
        return None
    seen.add(fp)
    return fp


def _backfill_scans(cur) -> int:
    cur.execute(
        """
        SELECT id::text, hf_repo, scan_metadata, tool_results, completed_at
        FROM public.scans
        WHERE config_json IS NULL
        ORDER BY completed_at DESC NULLS LAST
        """
    )
    rows = cur.fetchall()
    seen_fps = _existing_fingerprints(cur, "scans")
    count = 0
    for scan_id, hf_repo, scan_metadata, _tool_results, _completed_at in rows:
        meta = scan_metadata or {}
        options = meta.get("options") or {}
        cfg = normalize_scan_config(
            hf_repo=hf_repo,
            skip_modelscan=bool(options.get("skip_modelscan")),
            skip_fickling=bool(options.get("skip_fickling")),
            skip_modelaudit=bool(options.get("skip_modelaudit")),
            skip_deps=bool(options.get("skip_deps")),
            skip_secrets=bool(options.get("skip_secrets")),
        )
        fp = fingerprint("scan", cfg)
        cur.execute(
            """
            UPDATE public.scans
            SET visibility = 'public', owner_user_id = NULL,
                config_fingerprint = %(fp)s, config_json = %(cfg)s::jsonb
            WHERE id = %(id)s::uuid
            """,
            {"id": scan_id, "fp": _assign_fingerprint(fp, seen_fps), "cfg": jsonb_param(cfg)},
        )
        count += 1
    return count


def _backfill_safety(cur) -> int:
    cur.execute(
        """
        SELECT id::text, gateway_model_id, config_json, completed_at
        FROM public.safety_runs
        WHERE config_json IS NULL
        ORDER BY completed_at DESC NULLS LAST
        """
    )
    seen_fps = _existing_fingerprints(cur, "safety_runs")
    count = 0
    for run_id, model, existing_cfg, _completed_at in cur.fetchall():
        cfg = existing_cfg if isinstance(existing_cfg, dict) and existing_cfg else normalize_safety_config(model=model)
        if not cfg.get("model"):
            cfg = normalize_safety_config(model=model)
        fp = fingerprint("safety", cfg)
        cur.execute(
            """
            UPDATE public.safety_runs
            SET visibility = 'public', owner_user_id = NULL,
                config_fingerprint = %(fp)s, config_json = %(cfg)s::jsonb
            WHERE id = %(id)s::uuid
            """,
            {"id": run_id, "fp": _assign_fingerprint(fp, seen_fps), "cfg": jsonb_param(cfg)},
        )
        count += 1
    return count


def _backfill_eval(cur) -> int:
    cur.execute(
        """
        SELECT id::text, gateway_model_id, judge_model, adaptation, completed_at
        FROM public.eval_runs
        WHERE config_json IS NULL
        ORDER BY completed_at DESC NULLS LAST
        """
    )
    seen_fps = _existing_fingerprints(cur, "eval_runs")
    count = 0
    for run_id, candidate, judge, adaptation, _completed_at in cur.fetchall():
        ad = adaptation or {}
        suite = ad.get("task_suite_version") or ad.get("suite_key") or "unknown"
        max_tokens = int(ad.get("max_tokens") or 2000)
        cfg = normalize_eval_config(
            candidate=candidate,
            judge=judge or "",
            suite_key=str(suite),
            max_tokens=max_tokens,
        )
        fp = fingerprint("eval", cfg)
        vis = "public" if is_public_default("eval", cfg) else "public"
        cur.execute(
            """
            UPDATE public.eval_runs
            SET visibility = %(vis)s, owner_user_id = NULL,
                config_fingerprint = %(fp)s, config_json = %(cfg)s::jsonb
            WHERE id = %(id)s::uuid
            """,
            {"id": run_id, "fp": _assign_fingerprint(fp, seen_fps), "cfg": jsonb_param(cfg), "vis": vis},
        )
        count += 1
    return count


def _backfill_benchmarks(cur) -> int:
    cur.execute(
        """
        SELECT id::text, gateway_model_id, benchmark_key, completed_at
        FROM public.benchmark_runs
        WHERE config_json IS NULL
        ORDER BY completed_at DESC NULLS LAST
        """
    )
    seen_fps = _existing_fingerprints(cur, "benchmark_runs")
    count = 0
    for run_id, model, benchmark_key, _completed_at in cur.fetchall():
        cfg = normalize_benchmark_config(benchmark_key=benchmark_key, model=model)
        fp = fingerprint("benchmark", cfg)
        cur.execute(
            """
            UPDATE public.benchmark_runs
            SET visibility = 'public', owner_user_id = NULL,
                config_fingerprint = %(fp)s, config_json = %(cfg)s::jsonb
            WHERE id = %(id)s::uuid
            """,
            {"id": run_id, "fp": _assign_fingerprint(fp, seen_fps), "cfg": jsonb_param(cfg)},
        )
        count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill auth/visibility columns on pillar tables.")
    ap.add_argument("--apply", action="store_true", help="Write updates (default: dry run count only)")
    args = ap.parse_args()

    dsn = resolve_dsn("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")
    if not dsn:
        print("No DSN configured.", file=sys.stderr)
        return 1

    import psycopg

    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            scans = _backfill_scans(cur)
            safety = _backfill_safety(cur)
            evals = _backfill_eval(cur)
            benchmarks = _backfill_benchmarks(cur)
            print(
                f"Would update scans={scans} safety={safety} evals={evals} benchmarks={benchmarks}"
            )
            if args.apply:
                conn.commit()
                print("Applied.")
            else:
                conn.rollback()
                print("Dry run — pass --apply to commit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
