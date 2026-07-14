#!/usr/bin/env python3
"""
Batch-evaluate every candidate model across every eval suite, so the public
report-card gallery (/labels) shows a full set of MODEL LABELs.

For each (candidate model x suite) it builds the SAME runner invocation the web
"Start eval" flow uses (frontend.eval_launch.build_command) and runs it
synchronously. The judge is picked cross-family per the MT-Bench rule
(model_family(judge) != model_family(candidate)); execution-scored suites skip
the judge automatically. Results land in evaluator/results/, which the
file-backed frontend reads directly — Postgres ingest is a separate step
(dbutils/post_run.py or evaluator/db/load_results.py --apply), and requires the
rotated EFFICACY_DB_DSN.

SAFE BY DEFAULT: with no flags this only PRINTS the plan (a full sweep is ~200
gateway calls and costs money). Pass --run to actually execute.

Examples:
  # Show the full plan (no calls):
  uv run python scripts/run_all_models.py
  # Run one model on the judge-scored suites, real calls:
  uv run python scripts/run_all_models.py --run --models "GPT 4.1 Mini" \
      --suites it_support_v1,policy_qa_v1.1
  # Full sweep (needs DUKE_GATEWAY_KEY):
  uv run python scripts/run_all_models.py --run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _pick_judge(candidate: str, judges: tuple[str, ...]) -> str | None:
    """First calibrated judge from a different model family than the candidate
    (MT-Bench cross-family rule). None if every judge shares its family."""
    from frontend.eval_launch import model_family

    cand_family = model_family(candidate)
    for judge in judges:
        if model_family(judge) != cand_family:
            return judge
    return None


def _plan(models: list[str], suites: list[str], judges: tuple[str, ...]) -> list[dict]:
    """Every (candidate, suite, judge) job, skipping pairs with no cross-family
    judge (reported, never silently dropped)."""
    jobs: list[dict] = []
    for candidate in models:
        judge = _pick_judge(candidate, judges)
        for suite_key in suites:
            jobs.append({"candidate": candidate, "suite": suite_key, "judge": judge})
    return jobs


def _run_one(job: dict, max_tokens: int, timeout: int) -> tuple[bool, str]:
    """Build the web-identical runner argv and run it synchronously."""
    from frontend.eval_launch import build_command, predict_stem

    candidate, suite_key, judge = job["candidate"], job["suite"], job["judge"]
    if judge is None:
        return False, "no cross-family judge available"
    stem = predict_stem(suite_key, candidate)
    argv = build_command(candidate, judge, suite_key, max_tokens, stem)
    try:
        proc = subprocess.run(
            argv, cwd=str(REPO_ROOT / "evaluator"),
            timeout=timeout, capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, (tail[-1] if tail else f"exit {proc.returncode}")
    return True, stem


def main() -> int:
    from frontend.eval_launch import JUDGE_MODELS, SUITES, candidate_models

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true",
                    help="actually execute (default: print the plan only)")
    ap.add_argument("--models", default="",
                    help="comma-separated candidate models (default: all live)")
    ap.add_argument("--suites", default="",
                    help="comma-separated suite keys (default: all)")
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--timeout", type=int, default=1800,
                    help="per-run timeout in seconds (default: 1800)")
    ap.add_argument("--limit", type=int, default=0,
                    help="cap the number of jobs (0 = no cap)")
    args = ap.parse_args()

    models = ([m.strip() for m in args.models.split(",") if m.strip()]
              or list(candidate_models()))
    all_suites = list(SUITES.keys())
    suites = [s.strip() for s in args.suites.split(",") if s.strip()] or all_suites
    unknown = [s for s in suites if s not in SUITES]
    if unknown:
        print(f"ERROR: unknown suite(s): {', '.join(unknown)}")
        print(f"       known: {', '.join(all_suites)}")
        return 2

    jobs = _plan(models, suites, JUDGE_MODELS)
    if args.limit:
        jobs = jobs[: args.limit]

    print(f"{len(models)} model(s) x {len(suites)} suite(s) = {len(jobs)} job(s)")
    no_judge = [j for j in jobs if j["judge"] is None]
    if no_judge:
        pairs = ", ".join(sorted({j["candidate"] for j in no_judge}))
        print(f"  {len(no_judge)} job(s) have NO cross-family judge and will be "
              f"skipped: {pairs}")

    if not args.run:
        print("\nDRY RUN — nothing executed. Re-run with --run to launch.\n")
        for j in jobs:
            print(f"  {j['candidate']:24} {j['suite']:20} judge={j['judge']}")
        return 0

    print("\nRunning (results -> evaluator/results/) ...\n")
    ok = 0
    failures: list[str] = []
    for i, job in enumerate(jobs, 1):
        label = f"{job['candidate']} / {job['suite']}"
        started = time.strftime("%H:%M:%S", time.gmtime())
        print(f"[{i}/{len(jobs)}] {started}  {label} ...", flush=True)
        success, detail = _run_one(job, args.max_tokens, args.timeout)
        if success:
            ok += 1
            print(f"        ok  -> {detail}")
        else:
            failures.append(f"{label}: {detail}")
            print(f"        FAIL: {detail}")

    print(f"\nDone. {ok}/{len(jobs)} ok, {len(failures)} failed.")
    for f in failures:
        print(f"  FAIL {f}")
    print("\nNext: ingest into the public view once the DSN is rotated —")
    print("  uv run python evaluator/db/load_results.py --apply")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
