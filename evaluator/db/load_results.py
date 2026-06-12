"""
load_results.py — results JSONL -> the efficacy tables (efficacy_schema.sql).

Reads every results file under evaluator/results/ and loads it into
public.task_suites / eval_runs / eval_results. One JSONL line = one
eval_results row (the schema's Option A), so the transform is mostly a
re-labeling of fields the runner already wrote.

SAFE BY DEFAULT: without --apply this is a dry run — it prints what WOULD
be loaded and never opens a database connection. The shared Postgres is
only touched when you pass --apply AND a DSN (via --dsn or the
EFFICACY_DB_DSN / DATABASE_URL env vars), and only after the team has
reviewed efficacy_schema.sql.

Idempotent: re-running with --apply cannot duplicate rows — every INSERT
uses the schema's unique keys via ON CONFLICT DO NOTHING.

Run from the evaluator/ directory:
    python db/load_results.py                 # dry run (no DB needed)
    python db/load_results.py --apply         # real load (needs psycopg + DSN)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

EVALUATOR = Path(__file__).resolve().parent.parent
RESULTS_DIR = EVALUATOR / "results"


# ---------------------------------------------------------------------------
# Pure transforms: JSONL rows -> table-row dicts (no DB, fully unit-testable)
# ---------------------------------------------------------------------------


def split_suite_version(task_suite_version: str) -> tuple[str, str]:
    """'it_support_v1' -> ('it_support', 'v1'); 'policy_qa_v1.1' -> ('policy_qa', 'v1.1')."""
    if "_v" in task_suite_version:
        key, _, suffix = task_suite_version.rpartition("_v")
        return key, f"v{suffix}"
    return task_suite_version, "v?"


# rubric_version -> evaluator-relative rubric path, for task_suites.yaml_path.
# A static map on purpose: result rows don't record the path, and importing
# frontend/eval_launch.py from here would be the wrong dependency direction.
# Unknown rubrics load with yaml_path NULL; backfill by hand if needed
# (ON CONFLICT DO NOTHING won't update suites loaded before a map entry existed).
_RUBRIC_PATHS: dict[str, str] = {
    "it_support_v1": "tasks/rubrics/it_support.yaml",
    "it_support_v1.1": "tasks/rubrics/it_support_v1.1.yaml",
    "policy_qa_v1": "tasks/rubrics/policy_qa_v1.yaml",
}


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return int(s[f])
    return int(s[f] + (s[c] - s[f]) * (k - f))


def suite_row(rows: list[dict]) -> dict:
    """task_suites row for one results file."""
    adaptation = rows[0]["adaptation"]
    key, version = split_suite_version(adaptation["task_suite_version"])
    rubric_version = adaptation.get("rubric_version")
    return {
        "suite_key": key,
        "version": version,
        "rubric_version": rubric_version,
        "yaml_path": _RUBRIC_PATHS.get(rubric_version),
    }


def run_row(rows: list[dict], source_file: str) -> dict:
    """eval_runs row for one results file (aggregates precomputed here)."""
    first = rows[0]
    overalls = [r["overall"] for r in rows if r.get("overall") is not None]
    latencies = [r["operational"]["latency_ms"] for r in rows]
    return {
        "id": first["evaluation_run_id"],
        "gateway_model_id": first["adaptation"]["candidate_model"],
        "judge_model": first["adaptation"].get("judge_model"),
        "status": "complete",
        "aggregate_score": statistics.mean(overalls) if overalls else None,
        "latency_p50_ms": _percentile(latencies, 50),
        "latency_p95_ms": _percentile(latencies, 95),
        "tokens_in_total": sum(r["operational"]["prompt_tokens"] for r in rows),
        "tokens_out_total": sum(r["operational"]["completion_tokens"] for r in rows),
        "cost_usd_total": round(
            sum(r["operational"]["estimated_cost_usd"] for r in rows), 6
        ),
        "adaptation": first["adaptation"],
        "source_file": source_file,
        "started_at": rows[0]["timestamp"],
        "completed_at": rows[-1]["timestamp"],
    }


def result_rows(rows: list[dict]) -> list[dict]:
    """eval_results rows: one per question, dimension scores inside detail."""
    out = []
    for r in rows:
        op = r["operational"]
        out.append({
            "eval_run_id": r["evaluation_run_id"],
            "task_id": r["question_id"],
            "metric": "judge_score",
            "score": r.get("overall"),
            "latency_ms": op["latency_ms"],
            "tokens_in": op["prompt_tokens"],
            "tokens_out": op["completion_tokens"],
            "cost_usd": round(op["estimated_cost_usd"], 6),
            "candidate_failed": r.get("candidate_failed", False),
            "judge_failed": r.get("judge_failed", False),
            "detail": {
                "candidate_response": r.get("candidate_response", ""),
                "scores": r.get("scores", {}),
                "error": r.get("error"),
                # Row-contract version: future schema migrations need to know
                # which EvaluationResult shape each stored row conforms to.
                "schema_version": r.get("schema_version"),
            },
        })
    return out


def load_file(path: Path) -> tuple[dict, dict, list[dict]] | None:
    """Parse one results JSONL into (suite_row, run_row, result_rows).
    Returns None for empty/unparsable files (same tolerance as the frontend)."""
    try:
        with path.open("r", encoding="utf-8") as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return None
    if not rows:
        return None
    return suite_row(rows), run_row(rows, path.name), result_rows(rows)


# ---------------------------------------------------------------------------
# SQL — uses the schema's unique keys for idempotency
# ---------------------------------------------------------------------------

_SUITE_INSERT = """
INSERT INTO public.task_suites (suite_key, version, rubric_version, yaml_path)
VALUES (%(suite_key)s, %(version)s, %(rubric_version)s, %(yaml_path)s)
ON CONFLICT (suite_key, version) DO NOTHING
"""

_SUITE_SELECT = """
SELECT id FROM public.task_suites WHERE suite_key = %(suite_key)s AND version = %(version)s
"""

_RUN_INSERT = """
INSERT INTO public.eval_runs (
    id, suite_id, gateway_model_id, judge_model, status, aggregate_score,
    latency_p50_ms, latency_p95_ms, tokens_in_total, tokens_out_total,
    cost_usd_total, adaptation, source_file, started_at, completed_at)
VALUES (
    %(id)s, %(suite_id)s, %(gateway_model_id)s, %(judge_model)s, %(status)s,
    %(aggregate_score)s, %(latency_p50_ms)s, %(latency_p95_ms)s,
    %(tokens_in_total)s, %(tokens_out_total)s, %(cost_usd_total)s,
    %(adaptation)s::jsonb, %(source_file)s, %(started_at)s, %(completed_at)s)
ON CONFLICT (id) DO NOTHING
"""

_RESULT_INSERT = """
INSERT INTO public.eval_results (
    eval_run_id, task_id, metric, score, latency_ms, tokens_in, tokens_out,
    cost_usd, candidate_failed, judge_failed, detail)
VALUES (
    %(eval_run_id)s, %(task_id)s, %(metric)s, %(score)s, %(latency_ms)s,
    %(tokens_in)s, %(tokens_out)s, %(cost_usd)s, %(candidate_failed)s,
    %(judge_failed)s, %(detail)s::jsonb)
ON CONFLICT (eval_run_id, task_id, metric) DO NOTHING
"""


def load_into(conn, parsed: list[tuple[dict, dict, list[dict]]]) -> None:
    """All cursor work + one commit. `conn` is anything DB-API-shaped
    (a psycopg connection in production, a fake in tests): needs
    .cursor() as a context manager and .commit()."""
    with conn.cursor() as cur:
        for suite, run, results in parsed:
            cur.execute(_SUITE_INSERT, suite)
            cur.execute(_SUITE_SELECT, suite)
            suite_id = cur.fetchone()[0]

            run_params = {**run, "suite_id": suite_id,
                          "adaptation": json.dumps(run["adaptation"])}
            cur.execute(_RUN_INSERT, run_params)

            for res in results:
                cur.execute(_RESULT_INSERT,
                            {**res, "detail": json.dumps(res["detail"])})
    conn.commit()


def apply_to_db(dsn: str, parsed: list[tuple[dict, dict, list[dict]]]) -> None:
    """Connect and load everything in one transaction. Requires psycopg (v3)."""
    try:
        import psycopg
    except ImportError:
        sys.exit(
            "psycopg is required for --apply:  uv sync --group db"
        )

    with psycopg.connect(dsn) as conn:
        load_into(conn, parsed)
    print(f"Loaded {len(parsed)} run(s). Re-running is safe (ON CONFLICT DO NOTHING).")


def main() -> int:
    ap = argparse.ArgumentParser(description="Load results JSONLs into Postgres.")
    ap.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--apply", action="store_true",
                    help="actually write to the database (default: dry run)")
    ap.add_argument("--dsn", default=os.environ.get("EFFICACY_DB_DSN")
                    or os.environ.get("DATABASE_URL"),
                    help="Postgres DSN (or set EFFICACY_DB_DSN / DATABASE_URL)")
    args = ap.parse_args()

    files = sorted(p for p in args.results_dir.glob("*.jsonl")
                   if "_trace" not in p.name)
    parsed = [t for t in (load_file(p) for p in files) if t is not None]

    print(f"{len(parsed)} loadable run file(s) in {args.results_dir}:")
    for suite, run, results in parsed:
        print(f"  {run['source_file']}: suite={suite['suite_key']} {suite['version']}  "
              f"model={run['gateway_model_id']}  judge={run['judge_model']}  "
              f"score={run['aggregate_score'] and round(run['aggregate_score'], 2)}  "
              f"questions={len(results)}")

    if not args.apply:
        print("\nDry run (no database touched). Pass --apply with a DSN to load.")
        return 0
    if not args.dsn:
        sys.exit("--apply needs a DSN: pass --dsn or set EFFICACY_DB_DSN / DATABASE_URL")
    apply_to_db(args.dsn, parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
