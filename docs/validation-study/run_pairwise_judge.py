"""run_pairwise_judge.py — the Step-C producer.

Runs the reference-free pairwise LLM-judge over every item in item_pool.jsonl and
writes judge_prefs.jsonl ({item_id, judge_pref}) — the input analyze.py Step C
compares against the human consensus (Cohen's κ).

Each item pits its ``target_model`` against its ``opponent_model`` on the same
prompt. To control for position bias we judge each pair in BOTH orders and
combine:

    order 1: A = target,   B = opponent
    order 2: A = opponent,  B = target
    consistent  → judge_pref = the agreed winner (a system id, or "tie")
    disagree    → position-sensitive → judge_pref = "tie"  (and counted as a flip)

The judge is a cross-family model (Llama-4 Maverick by default) so it differs
from both the Qwen and the OpenAI systems (MT-Bench rule). Judgments are cached
in evaluator/cache/judges/, so a re-run is free and the swapped order is a
separate entry.

Usage:
    uv run python docs/validation-study/run_pairwise_judge.py            # full run
    uv run python docs/validation-study/run_pairwise_judge.py --limit 10 # pilot
    uv run python docs/validation-study/run_pairwise_judge.py --dry-run  # preview
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALUATOR = HERE.parent.parent / "evaluator"
sys.path.insert(0, str(EVALUATOR))

TIE = "tie"
PAIRWISE_PROMPT = EVALUATOR / "prompts" / "judge" / "pairwise_v1.txt"
DEFAULT_JUDGE = "Llama 4 Maverick"  # meta — cross-family to Qwen + OpenAI systems


def load_items(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip()]


def load_responses(path: Path) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            r = json.loads(ln)
            out[(r["source"], r["model"])] = r["text"]
    return out


def _winner_to_system(winner: str, sys_a: str, sys_b: str) -> str:
    """Map the judge's A/B/tie (for a given order) back to a system id / tie."""
    if winner == "A":
        return sys_a
    if winner == "B":
        return sys_b
    return TIE


def judge_item(item: dict, responses: dict, *, judge_model: str) -> dict | None:
    """Judge one item in both orders; combine into a position-bias-aware verdict.
    Returns a record dict, or None if a response text is missing."""
    from judge import judge_pairwise  # imported here so --dry-run needs no gateway

    source = item["source"]
    target, opponent = item["target_model"], item["opponent_model"]
    resp_t = responses.get((source, target))
    resp_o = responses.get((source, opponent))
    if resp_t is None or resp_o is None:
        return None

    kw = dict(question=item["prompt"], judge_model=judge_model,
              judge_prompt_path=PAIRWISE_PROMPT)
    r1 = judge_pairwise(response_a=resp_t, response_b=resp_o, **kw)
    r2 = judge_pairwise(response_a=resp_o, response_b=resp_t, **kw)

    if r1.failed or r2.failed:
        return {"item_id": item["item_id"], "failed": True,
                "error": r1.error or r2.error}

    sys1 = _winner_to_system(r1.winner, target, opponent)
    sys2 = _winner_to_system(r2.winner, opponent, target)
    flipped = sys1 != sys2
    judge_pref = sys1 if not flipped else TIE
    return {"item_id": item["item_id"], "judge_pref": judge_pref,
            "flipped": flipped, "order1": sys1, "order2": sys2}


def main() -> None:
    ap = argparse.ArgumentParser(description="Pairwise judge → judge_prefs.jsonl")
    ap.add_argument("--items", type=Path, default=HERE / "item_pool.jsonl")
    ap.add_argument("--responses", type=Path, default=HERE / "responses.jsonl")
    ap.add_argument("--out", type=Path, default=HERE / "judge_prefs.jsonl")
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE)
    ap.add_argument("--limit", type=int, default=None, help="only first N items (pilot)")
    ap.add_argument("--dry-run", action="store_true",
                    help="preview the planned comparisons; no API calls")
    args = ap.parse_args()

    items = load_items(args.items)
    responses = load_responses(args.responses)
    if args.limit:
        items = items[: args.limit]

    if args.dry_run:
        print(f"DRY RUN — {len(items)} item(s), judge={args.judge_model}\n")
        for it in items:
            src = it["source"]
            has = ((src, it["target_model"]) in responses and
                   (src, it["opponent_model"]) in responses)
            mark = "ok " if has else "MISSING responses"
            print(f"  {it['item_id']}  [{it.get('task_type','?'):>6}]  "
                  f"{it['target_model']}  vs  {it['opponent_model']}   ({mark})")
        print(f"\nWould run {len(items)} items x 2 orders = "
              f"{len(items) * 2} judge calls -> {args.out}")
        return

    records, written, failed, flips, ties = [], 0, 0, 0, 0
    for it in items:
        rec = judge_item(it, responses, judge_model=args.judge_model)
        if rec is None:
            print(f"  SKIP {it['item_id']} — missing response text", file=sys.stderr)
            continue
        if rec.get("failed"):
            failed += 1
            print(f"  FAIL {it['item_id']} — {rec.get('error')}", file=sys.stderr)
            continue
        records.append(rec)
        written += 1
        flips += int(rec["flipped"])
        ties += int(rec["judge_pref"] == TIE)
        print(f"  {rec['item_id']}: {rec['judge_pref']}"
              f"{'  (order-flip)' if rec['flipped'] else ''}")

    args.out.write_text(
        "\n".join(json.dumps({"item_id": r["item_id"], "judge_pref": r["judge_pref"]})
                  for r in records) + ("\n" if records else ""),
        encoding="utf-8")

    n = written or 1
    print(f"\nWrote {written} prefs -> {args.out}"
          f"   ({failed} failed)")
    print(f"Position-bias flip-rate: {flips}/{written} = {flips / n:.1%}"
          f"   |   ties: {ties}/{written} = {ties / n:.1%}")


if __name__ == "__main__":
    main()
