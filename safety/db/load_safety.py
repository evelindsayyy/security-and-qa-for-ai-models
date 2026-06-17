"""
load_safety.py — merged_safety_result.json -> public.safety_runs / public.safety_findings.

Reads every ``merged_safety_result.json`` under ``safety/output/<model>/`` and loads
validated ``MergedSafetyResult`` rows into Postgres. Uses shared ``dbutils`` for env,
file IO, connect, JSONB params, and the dry-run CLI contract.

SAFE BY DEFAULT: without ``--apply`` this is a dry run — it prints what WOULD
be loaded and never opens a database connection.

Idempotent: re-running with ``--apply`` cannot duplicate rows — every INSERT
uses ON CONFLICT DO NOTHING on the schema unique keys.

Run from repo root:
    uv run python safety/db/load_safety.py                 # dry run
    uv run python safety/db/load_safety.py --apply         # real load (needs psycopg + DSN)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dbutils import apply_loader, iter_files, jsonb_param, load_repo_env, read_json
from dbutils.cli import add_ingest_arguments
from dbutils.ingest import exit_if_apply_without_dsn, print_dry_run_hint
from safety.schemas import MergedSafetyResult

SAFETY = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SAFETY / "output"


# ---------------------------------------------------------------------------
# Pure transforms — no DB, unit-testable
# ---------------------------------------------------------------------------


def _parse_iso_timestamp(value: str | None) -> str | None:
    if not value or value == "—":
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        datetime.fromisoformat(normalized)
        return normalized
    except ValueError:
        return None


def safety_run_row(data: dict[str, Any]) -> dict:
    """One ``safety_runs`` row from a validated MergedSafetyResult dict."""

    def _tier(v) -> str:
        return str(v.value if hasattr(v, "value") else v).lower()

    return {
        "model_id": None,
        "gateway_model_id": data["gateway_model_id"],
        "display_name": data.get("display_name"),
        "status": data.get("status") or "complete",
        "deployment_context": data.get("deployment_context") or {},
        "summary_pass_rate": float(data.get("summary_pass_rate") or 0.0),
        "safety_tier": _tier(data.get("safety_tier", "low")),
        "adversarial_tier": _tier(data.get("adversarial_tier", "low")),
        "composite_tier": _tier(data.get("composite_tier", "low")),
        "composite_score": float(data.get("composite_score") or 0.0),
        "missing_suites": data.get("missing_suites") or [],
        "runs": data.get("runs") or [],
        "tool_results": data.get("tool_results") or {},
        "started_at": _parse_iso_timestamp(data.get("started_at")),
        "completed_at": _parse_iso_timestamp(data.get("completed_at")),
    }


def finding_rows(data: dict[str, Any]) -> list[dict]:
    """``safety_findings`` rows for one safety run."""
    rows: list[dict] = []
    for raw in data.get("findings") or []:
        if not isinstance(raw, dict):
            continue
        sev = raw.get("severity", "unknown")
        if hasattr(sev, "value"):
            sev = sev.value
        rows.append(
            {
                "finding_key": raw.get("id") or "",
                "category": (raw.get("category") or "unknown").lower(),
                "source": (raw.get("source") or "unknown").lower(),
                "passed": bool(raw.get("passed", False)),
                "severity": str(sev).lower(),
                "title": raw.get("title") or "—",
                "description": (raw.get("description") or "").strip(),
                "probe_id": raw.get("probe_id") or "",
                "probe_suite": raw.get("probe_suite"),
                "corroborated_by": raw.get("corroborated_by"),
            }
        )
    return rows


def load_file(path: Path) -> tuple[dict, list[dict]] | None:
    """Parse one ``merged_safety_result.json`` into (run_row, finding_rows).

    Returns None for empty/unparsable files or results missing completed_at.
    """
    data = read_json(path)
    if data is None:
        return None
    try:
        validated = MergedSafetyResult.model_validate(data)
        payload = validated.model_dump(mode="json")
    except Exception:
        return None

    run = safety_run_row(payload)
    if not run["completed_at"]:
        return None
    findings = finding_rows(payload)
    return run, findings


# ---------------------------------------------------------------------------
# SQL — idempotent INSERTs keyed to safety_schema.sql UNIQUE constraints
# ---------------------------------------------------------------------------

_RUN_INSERT = """
INSERT INTO public.safety_runs (
    model_id, gateway_model_id, display_name, status, deployment_context,
    summary_pass_rate, safety_tier, adversarial_tier, composite_tier,
    composite_score, missing_suites, runs, tool_results, started_at, completed_at)
VALUES (
    %(model_id)s, %(gateway_model_id)s, %(display_name)s, %(status)s,
    %(deployment_context)s::jsonb, %(summary_pass_rate)s, %(safety_tier)s,
    %(adversarial_tier)s, %(composite_tier)s, %(composite_score)s,
    %(missing_suites)s::jsonb, %(runs)s::jsonb, %(tool_results)s::jsonb,
    %(started_at)s, %(completed_at)s)
ON CONFLICT (gateway_model_id, completed_at) DO NOTHING
"""

_RUN_SELECT = """
SELECT id FROM public.safety_runs
WHERE gateway_model_id = %(gateway_model_id)s AND completed_at = %(completed_at)s
"""

_FINDING_INSERT = """
INSERT INTO public.safety_findings (
    run_id, finding_key, category, source, passed, severity, title, description,
    probe_id, probe_suite, corroborated_by)
VALUES (
    %(run_id)s, %(finding_key)s, %(category)s, %(source)s, %(passed)s,
    %(severity)s, %(title)s, %(description)s, %(probe_id)s, %(probe_suite)s,
    %(corroborated_by)s::jsonb)
ON CONFLICT (run_id, finding_key) DO NOTHING
"""


def _run_params(run: dict) -> dict:
    return {
        **run,
        "deployment_context": jsonb_param(run["deployment_context"]),
        "missing_suites": jsonb_param(run["missing_suites"]),
        "runs": jsonb_param(run["runs"]),
        "tool_results": jsonb_param(run["tool_results"]),
    }


def load_into(conn, parsed: list[tuple[dict, list[dict]]]) -> None:
    """All cursor work + one commit. ``conn`` is DB-API-shaped (psycopg or fake)."""
    with conn.cursor() as cur:
        for run, findings in parsed:
            params = _run_params(run)
            cur.execute(_RUN_INSERT, params)
            cur.execute(_RUN_SELECT, params)
            row = cur.fetchone()
            if not row:
                continue
            run_id = row[0]

            for finding in findings:
                if not finding["finding_key"]:
                    continue
                fparams = {
                    **finding,
                    "run_id": run_id,
                    "corroborated_by": jsonb_param(finding["corroborated_by"])
                    if finding.get("corroborated_by") is not None
                    else None,
                }
                cur.execute(_FINDING_INSERT, fparams)
    conn.commit()


def main() -> int:
    load_repo_env()
    ap = argparse.ArgumentParser(
        description="Load merged_safety_result.json files into Postgres."
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="safety output root (default: safety/output)",
    )
    add_ingest_arguments(ap, dsn_env_keys=("POSTGRES_DSN", "DATABASE_URL"))
    args = ap.parse_args()

    paths = iter_files(args.output_dir, "*/merged_safety_result.json")
    parsed = [t for t in (load_file(p) for p in paths) if t is not None]

    print(f"{len(parsed)} loadable safety run(s) in {args.output_dir}:")
    for run, findings in parsed:
        print(
            f"  {run['gateway_model_id']}:  "
            f"composite_tier={run['composite_tier']}  "
            f"score={run['composite_score']:.2f}  "
            f"findings={len(findings)}  "
            f"completed_at={run['completed_at']}"
        )

    if not args.apply:
        print_dry_run_hint()
        return 0
    exit_if_apply_without_dsn(args.dsn)
    apply_loader(
        args.dsn,
        lambda conn: load_into(conn, parsed),
        item_count=len(parsed),
        item_label="safety run(s)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
