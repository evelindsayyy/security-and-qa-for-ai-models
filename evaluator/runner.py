"""
runner.py

Orchestration: loops over the suite questions, calls generate_candidate
(Monday's), then judge_response (Tuesday's) when the candidate succeeded,
computes the rubric's weighted-normalized overall, and writes one
EvaluationResult row per question to a results JSONL file.

CLI (defaults make a normal invocation short):

    python runner.py --candidate-model gpt-5-chat \\
                     --judge-model "Llama 4 Maverick"

Output, both inside results/:
    <UTC-timestamp>_<suite>_<candidate>.jsonl       (one EvaluationResult per line)
    <UTC-timestamp>_<suite>_<candidate>_trace.jsonl (raw responses for debugging)

Hard rule from CLAUDE.md: the runner never crashes. A per-question
failure is written to the row with the appropriate flag and error
string; the loop keeps going. Re-runs are cheap because both
generate_candidate and judge_response are cached.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from candidate import generate_candidate
from judge import judge_response, resolve_rubric
from schemas import (
    SCHEMA_VERSION,
    Adaptation,
    DimensionScore,
    EvaluationResult,
    Operational,
    new_run_id,
    now_iso,
)


HERE = Path(__file__).parent


# ---------------------------------------------------------------------------
# Pricing table (Duke Gateway — snapshot 2026-06-03)
# ---------------------------------------------------------------------------
# Per 1M tokens, (input_rate_usd, output_rate_usd). Keys are the exact
# Gateway model identifier strings (case- and space-sensitive). Models not
# in this table get cost recorded as 0.0 with a stderr warning — better
# honest zero than fabricated cost.
#
# When Duke updates the rate sheet, edit this dict. Past result rows keep
# their original cost numbers (snapshot at write time).
# ---------------------------------------------------------------------------

_COST_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # GPT-5 family
    "gpt-5":          (1.25, 10.00),
    "gpt-5-chat":     (1.25, 10.00),
    "gpt-5-mini":     (0.25,  2.00),
    "gpt-5-nano":     (0.05,  0.40),
    "gpt-5.1":        (1.25, 10.00),
    "gpt-5.1-chat":   (1.25, 10.00),
    "gpt-5.2":        (1.75, 14.00),
    "gpt-5.2-chat":   (1.75, 14.00),
    "gpt-5.3-chat":   (1.75, 14.00),
    "gpt-5.4":        (2.50, 15.00),
    "gpt-5.5":        (2.50, 15.00),
    # GPT-4.1 family — note: Gateway allowlist returns these with spaces and
    # capitals (e.g. "GPT 4.1 Mini"), not the rate-sheet's hyphenated form.
    # Keys must match the model id the user passes via --candidate-model.
    "GPT 4.1":        (2.00,  8.00),
    "GPT 4.1 Mini":   (0.40,  1.60),
    "GPT 4.1 Nano":   (0.10,  0.40),
    # GPT-OSS
    "gpt-oss-120b":   (0.15,  0.60),
    # Llama family (note: exact strings have spaces and capitals)
    "Llama 3.3":          (0.71, 0.71),
    "Llama 4 Maverick":   (0.35, 1.41),
    "Llama 4 Scout":      (0.20, 0.78),
}


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = _COST_PER_M_TOKENS.get(model)
    if rates is None:
        print(
            f"  WARN: no pricing entry for model {model!r}; cost recorded as 0.0",
            file=sys.stderr,
        )
        return 0.0
    in_rate, out_rate = rates
    return (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate


# ---------------------------------------------------------------------------
# Rubric-driven weighted overall
# ---------------------------------------------------------------------------


def _weighted_overall(
    scores: dict[str, DimensionScore], rubric: dict
) -> Optional[float]:
    """Apply the rubric's aggregation formula to per-dimension scores.

    Formula (from rubric YAML):
        overall = sum( weight_i * (score_i / max_i) )    # in [0, 1]
        display = round(overall * display_scale, 2)

    Returns None if any rubric dimension is missing from `scores`.
    """
    dim_blocks = rubric.get("dimensions", {})
    if any(dim not in scores for dim in dim_blocks):
        return None
    normalized = 0.0
    for dim, block in dim_blocks.items():
        max_score = block["scale"][1]
        weight = block["weight"]
        normalized += weight * (scores[dim].score / max_score)
    display_scale = rubric.get("aggregation", {}).get("display_scale", 5)
    return round(normalized * display_scale, 2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluator pipeline runner.")
    p.add_argument("--candidate-model", required=True,
                   help="Gateway model id (e.g. 'gpt-5-chat')")
    p.add_argument("--judge-model", required=True,
                   help="Gateway model id (e.g. 'Llama 4 Maverick')")
    p.add_argument("--suite", type=Path,
                   default=HERE / "tasks" / "it_support_v1.jsonl")
    p.add_argument("--rubric", type=Path,
                   default=HERE / "tasks" / "rubrics" / "it_support.yaml")
    p.add_argument("--system-prompt", type=Path,
                   default=HERE / "prompts" / "system" / "it_support_v1.txt")
    # NOTE: v1 hardcodes the four IT-support dims in its OUTPUT FORMAT and
    # only works with the it_support rubric; other rubrics need a template
    # with the {output_schema} placeholder (reference_based_v2.txt). main()
    # fails fast on a mismatched pairing. The default stays v1 so default
    # runs keep the judge cache and version string comparable with week 3.
    p.add_argument("--judge-prompt", type=Path,
                   default=HERE / "prompts" / "judge" / "reference_based_v1.txt")
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--max-tokens", type=int, default=500)
    # Reasoning judges (e.g. gpt-oss-120b) spend hidden thinking tokens from
    # the same budget; 600 leaves them no room for the ~200-token JSON verdict
    # and they come back empty/truncated. Raise to ~2000 for those judges.
    p.add_argument("--judge-max-tokens", type=int, default=600,
                   help="completion budget for judge calls (default 600; "
                        "use 2000+ for reasoning-model judges)")
    p.add_argument("--output-dir", type=Path, default=HERE / "results")
    # Lets a caller (the frontend launch flow) dictate the results filename
    # stem so it can predict the output path before the run starts. The
    # default keeps the runner's own <timestamp>_<suite>_<candidate> naming.
    p.add_argument("--output-name", type=str, default=None,
                   help="results filename stem (default: <timestamp>_<suite>_<candidate>)")
    return p.parse_args()


def _safe_slug(s: str) -> str:
    """Filename-safe version of a model id (spaces/specials → '-')."""
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in s)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    args = _parse_args()

    # ---- load contracts ----
    suite_lines = args.suite.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(suite_lines[0])
    suite_id = metadata.get("task_suite_version", args.suite.stem)
    # Task family without the version suffix ('policy_qa_v1' -> 'policy_qa'),
    # matching the schema's `suite` field semantics.
    suite_family = suite_id.rsplit("_v", 1)[0]
    questions = [json.loads(line) for line in suite_lines[1:] if line.strip()]

    # resolve_rubric inlines any {from: shared} references against
    # _shared_dimensions.yaml so rubric["dimensions"][dim] always has the
    # full scale/weight/anchors block _weighted_overall expects. For inline
    # rubrics (like the locked it_support_v1.yaml) this is a no-op.
    rubric, rubric_raw = resolve_rubric(args.rubric)
    rubric_version = rubric.get("rubric_version", args.rubric.stem)

    system_prompt = args.system_prompt.read_text(encoding="utf-8")
    system_prompt_version = args.system_prompt.stem
    judge_prompt_version = args.judge_prompt.stem

    # Fail fast on a judge-prompt/rubric mismatch. A template without the
    # {output_schema} placeholder (like the locked reference_based_v1) has
    # its dimension keys hardcoded in its OUTPUT FORMAT block; running it
    # against a rubric with a different dimension set would fail every
    # judge call twice (the parse retry) before producing an all-failed
    # run. Catch the pairing here, before any API call.
    judge_template = args.judge_prompt.read_text(encoding="utf-8")
    if "{output_schema}" not in judge_template:
        rubric_dims = tuple((rubric.get("dimensions") or {}).keys())
        missing = [d for d in rubric_dims if f'"{d}"' not in judge_template]
        if missing:
            print(
                f"ERROR: judge prompt {args.judge_prompt.name!r} hardcodes its "
                f"output dimensions and does not cover rubric dimension(s) "
                f"{missing} from rubric {rubric_version!r}. Use a rubric-aware "
                f"template instead, e.g.\n"
                f"  --judge-prompt {HERE / 'prompts' / 'judge' / 'reference_based_v2.txt'}",
                file=sys.stderr,
            )
            return 2

    # ---- prepare output paths ----
    run_id = new_run_id()
    run_started_filename = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cand_slug = _safe_slug(args.candidate_model)
    stem = (
        _safe_slug(args.output_name)
        if args.output_name
        else f"{run_started_filename}_{suite_id}_{cand_slug}"
    )
    out_path = args.output_dir / f"{stem}.jsonl"
    trace_path = args.output_dir / f"{stem}_trace.jsonl"

    # ---- banner ----
    print(f"Runner started  run_id={run_id}")
    print(f"  candidate: {args.candidate_model}    judge: {args.judge_model}")
    print(f"  suite: {suite_id} ({len(questions)} questions)    rubric: {rubric_version}")
    print(f"  output: {out_path}")
    print()

    counts = {"ok": 0, "candidate_failed": 0, "judge_failed": 0}
    t_run_start = time.perf_counter()
    candidate_model_version = time.strftime("Gateway %Y-%m", time.gmtime())

    with out_path.open("w", encoding="utf-8") as out_f, \
         trace_path.open("w", encoding="utf-8") as trace_f:

        for i, q in enumerate(questions, start=1):
            qid = q.get("id", f"unknown-{i}")
            try:
                # ---- candidate ----
                t0 = time.perf_counter()
                cand = generate_candidate(
                    question=q["question"],
                    model=args.candidate_model,
                    system_prompt=system_prompt,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                )
                cand_dur = time.perf_counter() - t0

                # ---- judge (only if candidate succeeded) ----
                judge_verdict = None
                judge_dur = 0.0
                if not cand.failed:
                    t1 = time.perf_counter()
                    judge_verdict = judge_response(
                        question=q["question"],
                        reference=q["reference"],
                        candidate_response=cand.response,
                        rubric_path=args.rubric,
                        judge_model=args.judge_model,
                        judge_prompt_path=args.judge_prompt,
                        max_tokens=args.judge_max_tokens,
                    )
                    judge_dur = time.perf_counter() - t1

                # ---- aggregate ----
                if cand.failed:
                    scores: dict[str, DimensionScore] = {}
                    overall: Optional[float] = None
                    judge_failed_flag = False
                    error = cand.error
                elif judge_verdict is not None and judge_verdict.failed:
                    scores = {}
                    overall = None
                    judge_failed_flag = True
                    error = judge_verdict.error
                else:
                    scores = judge_verdict.scores  # type: ignore[union-attr]
                    overall = _weighted_overall(scores, rubric)
                    judge_failed_flag = False
                    error = None

                # ---- build row ----
                adaptation = Adaptation(
                    candidate_model=args.candidate_model,
                    candidate_model_version=candidate_model_version,
                    system_prompt_version=system_prompt_version,
                    user_prompt_template_version="raw_question_v1",
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                    task_suite_version=suite_id,
                    rubric_version=rubric_version,
                    judge_model=args.judge_model,
                    judge_prompt_version=judge_prompt_version,
                )
                operational = Operational(
                    latency_ms=cand.latency_ms,
                    prompt_tokens=cand.prompt_tokens,
                    completion_tokens=cand.completion_tokens,
                    estimated_cost_usd=_estimate_cost_usd(
                        args.candidate_model, cand.prompt_tokens, cand.completion_tokens
                    ),
                )
                row = EvaluationResult(
                    evaluation_run_id=run_id,
                    timestamp=now_iso(),
                    question_id=qid,
                    suite=suite_family,
                    schema_version=SCHEMA_VERSION,
                    adaptation=adaptation,
                    candidate_response=cand.response,
                    scores=scores,
                    overall=overall,
                    operational=operational,
                    candidate_failed=cand.failed,
                    judge_failed=judge_failed_flag,
                    error=error,
                )
                out_f.write(row.to_jsonl() + "\n")
                out_f.flush()

                # ---- trace (raw bytes for debugging) ----
                trace_f.write(json.dumps({
                    "question_id": qid,
                    "candidate_response": cand.response,
                    "judge_raw_response": (
                        judge_verdict.raw_response if judge_verdict else ""
                    ),
                }, ensure_ascii=False) + "\n")
                trace_f.flush()

                # ---- bucket + progress line ----
                if cand.failed:
                    counts["candidate_failed"] += 1
                    status = f"CAND_FAIL ({(cand.error or '')[:40]})"
                elif judge_verdict is not None and judge_verdict.failed:
                    counts["judge_failed"] += 1
                    status = f"JUDGE_FAIL ({(judge_verdict.error or '')[:40]})"
                else:
                    counts["ok"] += 1
                    status = f"overall={overall}"

                print(
                    f"[{i:>2}/{len(questions)}] {qid}  "
                    f"cand={cand_dur:>4.1f}s tok={cand.prompt_tokens}/{cand.completion_tokens}  "
                    f"judge={judge_dur:>4.1f}s  {status}"
                )

            except Exception as e:
                # Defensive — generate_candidate / judge_response are documented
                # as no-raise, so reaching here means something else went wrong
                # (e.g. a malformed suite line). Record as a candidate failure
                # (closest bucket), still write a row so the JSONL has one row
                # per question, and continue.
                counts["candidate_failed"] += 1
                fallback = EvaluationResult(
                    evaluation_run_id=run_id,
                    timestamp=now_iso(),
                    question_id=qid,
                    suite=suite_family,
                    schema_version=SCHEMA_VERSION,
                    adaptation=Adaptation(
                        candidate_model=args.candidate_model,
                        candidate_model_version=candidate_model_version,
                        system_prompt_version=system_prompt_version,
                        user_prompt_template_version="raw_question_v1",
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                        task_suite_version=suite_id,
                        rubric_version=rubric_version,
                        judge_model=args.judge_model,
                        judge_prompt_version=judge_prompt_version,
                    ),
                    candidate_response="",
                    scores={},
                    overall=None,
                    operational=Operational(
                        latency_ms=0,
                        prompt_tokens=0,
                        completion_tokens=0,
                        estimated_cost_usd=0.0,
                    ),
                    candidate_failed=True,
                    judge_failed=False,
                    error=f"runner exception: {type(e).__name__}: {e}",
                )
                try:
                    out_f.write(fallback.to_jsonl() + "\n")
                    out_f.flush()
                except Exception as write_err:
                    print(
                        f"[{i:>2}/{len(questions)}] {qid}  "
                        f"FAILED to write fallback row: {write_err}",
                        file=sys.stderr,
                    )
                print(
                    f"[{i:>2}/{len(questions)}] {qid}  RUNNER_EXC: {type(e).__name__}: {e}",
                    file=sys.stderr,
                )

    # ---- final summary ----
    elapsed = time.perf_counter() - t_run_start
    print()
    print(
        f"Run complete in {elapsed:.1f}s — "
        f"{counts['ok']} OK, "
        f"{counts['candidate_failed']} candidate_failed, "
        f"{counts['judge_failed']} judge_failed"
    )
    print(f"Results: {out_path}")
    print(f"Trace:   {trace_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
