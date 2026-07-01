"""
execution_eval.py — execution-based functional scoring (text-to-SQL).

A reference-free, EXECUTABLE signal: the candidate produces SQL, we RUN it
against a throwaway in-memory SQLite database and check the result set equals
the expected answer. Unlike the LLM judge (subjective) or ROUGE-L (surface
word-overlap), this is ground truth — the query either returns the right rows
or it doesn't. (Inspired by execution-based code evaluation — Zhou et al.,
"Execution-Based Evaluation for Open-Domain Code Generation".)

SECURITY: candidate SQL runs ONLY in an in-memory `sqlite3` database
(`:memory:`) with a wall-clock timeout, no filesystem, no network, and no
extension loading; ATTACH/DETACH are rejected (the one in-memory escape to the
filesystem). Blast radius = the throwaway database. Arbitrary Python execution
is explicitly NOT performed. The `setup` (schema + seed) comes from the suite
(trusted, authored with the benchmark); only the candidate's query is untrusted.

Standalone post-processing, mirroring reference_metrics.py — run after a results
file exists:

    python -m evaluator.execution_eval --results results/<run>.jsonl [--suite sql_duke_v1]
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import threading
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"

_TIMEOUT_S = 5.0
# In-memory SQLite has no filesystem access EXCEPT via ATTACH (which can open a
# file DB). Reject it (and DETACH) so a candidate query can't reach disk.
_FORBIDDEN = re.compile(r"\b(attach|detach)\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Safe execution
# ---------------------------------------------------------------------------


def _strip_fence(text: str) -> str:
    """Drop a leading ```lang fence and trailing ``` (plus surrounding whitespace).
    Shared by every checker — models wrap SQL, JSON, and numbers in fences alike."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def strip_sql(text: str) -> str:
    """Pull SQL out of a model response — drop ```sql fences and surrounding prose."""
    return _strip_fence(text)


def run_sql(candidate_sql: str, setup: str) -> tuple[list | None, str | None]:
    """Run `setup` then the candidate query in a fresh in-memory SQLite.

    Returns (rows, error): rows is a list of tuples on success, else None with
    a one-line error string. A query exceeding _TIMEOUT_S is interrupted.
    """
    sql = strip_sql(candidate_sql)
    if not sql:
        return None, "empty SQL"
    if _FORBIDDEN.search(sql):
        return None, "forbidden statement (attach/detach)"

    conn = sqlite3.connect(":memory:")
    # Interrupt the candidate query if it runs too long (set on another thread,
    # which is how sqlite3.interrupt is meant to be used).
    timer = threading.Timer(_TIMEOUT_S, conn.interrupt)
    try:
        conn.executescript(setup)        # trusted schema + seed (untimed)
        timer.start()
        rows = conn.execute(sql).fetchall()   # untrusted candidate query (timed)
        return rows, None
    except Exception as e:               # never crash the scorer
        return None, f"{type(e).__name__}: {e}"
    finally:
        timer.cancel()
        conn.close()


def _normalize(rows: list) -> list:
    """Order-insensitive view of a result set (rows compared as a multiset)."""
    return sorted((tuple(r) for r in rows),
                  key=lambda r: tuple(str(x) for x in r))


def passed(candidate_rows: list | None, expected: list) -> bool:
    """True iff the candidate's result set equals `expected`, order-insensitive."""
    if candidate_rows is None:
        return False
    return _normalize(candidate_rows) == _normalize([tuple(r) for r in expected])


# ---------------------------------------------------------------------------
# Scoring a results file against its suite
# ---------------------------------------------------------------------------


def load_suite(suite_version: str) -> dict[str, dict]:
    """question_id -> task dict (the row minus 'id') from tasks/<suite_version>.jsonl.

    The metadata line (no 'id') is skipped; only execution rows are kept. An
    execution row carries at least 'expected'; 'setup' is SQL-specific (other
    check types carry only their own fields)."""
    path = TASKS_DIR / f"{suite_version}.jsonl"
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if "id" in row and "expected" in row:
            out[row["id"]] = {k: v for k, v in row.items() if k != "id"}
    return out


def suite_check_type(suite_version: str) -> str:
    """The execution checker a suite uses (default 'sql'), from its metadata line."""
    path = TASKS_DIR / f"{suite_version}.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        meta = json.loads(line)
        if "id" not in meta:                 # the metadata line
            return meta.get("check", "sql")
        break                                # first row had an id -> no metadata
    return "sql"


# ---------------------------------------------------------------------------
# Checker registry — one entry per execution task type. A checker takes the
# candidate's response + the task dict and returns (passed, error). A suite's
# `check` metadata field selects which one runs; new task types plug in HERE
# without touching the runner or the schema.
# ---------------------------------------------------------------------------


def _check_sql(candidate_response: str, task: dict) -> tuple[bool, str | None]:
    """Run the candidate SQL against the task's `setup`; compare rows to `expected`."""
    rows, err = run_sql(candidate_response, task["setup"])
    if err is not None:
        return False, err
    return passed(rows, task["expected"]), None


def _check_json(candidate_response: str, task: dict) -> tuple[bool, str | None]:
    """Parse the candidate's response as JSON and compare to `expected`.

    Object key order is irrelevant (Python dict equality); array order IS
    significant; numbers compare by value (1 == 1.0). Unparseable input fails
    cleanly rather than crashing the scorer."""
    raw = _strip_fence(candidate_response)
    if not raw:
        return False, "empty response"
    try:
        got = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        return False, f"invalid JSON: {e}"
    return got == task["expected"], None


_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _extract_number(text: str) -> float | None:
    """Best-effort single number from a model response. Tries the whole string
    first (after stripping a fence, `$`, thousands commas, and a trailing `%`),
    else falls back to the LAST number-looking token (answers usually end with
    it). Returns None when there's no number to parse."""
    t = _strip_fence(text)
    cleaned = t.strip().lstrip("$").rstrip("%").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        pass
    nums = _NUMBER_RE.findall(t)
    if not nums:
        return None
    try:
        return float(nums[-1].replace(",", ""))
    except ValueError:
        return None


def _check_numeric(candidate_response: str, task: dict) -> tuple[bool, str | None]:
    """Extract a number from the response and compare to `expected` within an
    optional absolute `tolerance` (default near-exact; `rel_tol` guards float
    representation so 42.0 matches 42)."""
    got = _extract_number(candidate_response)
    if got is None:
        return False, "no number found in response"
    expected = float(task["expected"])
    tol = float(task.get("tolerance", 0.0))
    if math.isclose(got, expected, rel_tol=1e-9, abs_tol=tol):
        return True, None
    return False, f"got {got}, expected {expected} (tol {tol})"


CHECKERS: dict[str, Callable[[str, dict], tuple]] = {
    "sql": _check_sql,
    "json": _check_json,
    "numeric": _check_numeric,
}


def score_results_file(results_path: Path, suite_version: str | None = None) -> dict:
    """Functional pass/fail per question for a results JSONL, by executing each
    candidate's SQL against the suite's setup and comparing to expected.

    Carries the judge's ``overall`` along so execution and judge can be compared
    side by side (the "functional vs surface/subjective" story)."""
    rows = [json.loads(line) for line in
            results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return {"results_file": results_path.name, "n": 0, "rows": []}

    if suite_version is None:
        suite_version = rows[0].get("adaptation", {}).get("task_suite_version", "")
    suite = load_suite(suite_version)
    check_type = suite_check_type(suite_version)
    checker = CHECKERS.get(check_type)
    if checker is None:
        raise ValueError(
            f"unknown execution check type {check_type!r} for suite "
            f"{suite_version!r} (known: {sorted(CHECKERS)})")

    scored = []
    for r in rows:
        qid = r.get("question_id")
        if qid not in suite:
            continue
        ok, err = checker(r.get("candidate_response", ""), suite[qid])
        scored.append({
            "question_id": qid,
            "passed": ok,
            "error": err,
            "judge_overall": r.get("overall"),
        })

    n = len(scored)
    npass = sum(1 for s in scored if s["passed"])
    return {
        "results_file": results_path.name,
        "suite_version": suite_version,
        "check": check_type,
        "candidate_model": rows[0].get("adaptation", {}).get("candidate_model", ""),
        "n": n,
        "passed": npass,
        "pass_rate": round(npass / n, 4) if n else 0.0,
        "rows": scored,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Execution-based (SQL) functional scoring for a results JSONL.")
    ap.add_argument("--results", type=Path, required=True,
                    help="results JSONL whose candidate_response field holds SQL")
    ap.add_argument("--suite", default=None,
                    help="suite version override (default: read from the run)")
    args = ap.parse_args()

    out = score_results_file(args.results, args.suite)
    print(f"{out['results_file']}  model={out.get('candidate_model', '')}  "
          f"suite={out.get('suite_version', '')}  n={out['n']}")
    print(f"  pass-rate: {out['passed']}/{out['n']} = {out['pass_rate']}")
    print(f"  {'question':<10}{'exec':>7}{'judge':>8}")
    for s in out["rows"]:
        mark = "PASS" if s["passed"] else "fail"
        flag = f"  ({s['error']})" if s["error"] else ""
        print(f"  {s['question_id']:<10}{mark:>7}{str(s['judge_overall']):>8}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
