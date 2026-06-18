"""
reference_metrics.py — reference-based automatic metrics (ROUGE-L).

A SECOND, measured signal for summarization, independent of the LLM judge:
how much of the reference summary's wording the candidate reproduces. Per HELM,
multi-metric reporting — the judge scores meaning (faithfulness/coverage), while
ROUGE-L scores lexical overlap. They can disagree, and that disagreement is
itself a finding (e.g. a faithful paraphrase scores high with the judge but low
on ROUGE-L because it reuses few of the reference's exact words).

Standalone by design: no schema change, no judge involvement, no new dependency
(pure-Python LCS). Run it after a results file exists:

    python -m evaluator.reference_metrics --results results/<run>.jsonl
    python -m evaluator.reference_metrics --results results/<run>.jsonl --bertscore

ROUGE-L here is the token-level longest-common-subsequence F-measure (the common
single-reference simplification). Sentence-union ROUGE-L is deliberately
deferred. References are AI-drafted and not expert-validated, so these numbers
are methodology validation, not authoritative scores (same posture as the judge
scores on placeholder references).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"

_WORD = re.compile(r"\w+")


# ---------------------------------------------------------------------------
# Core ROUGE-L (pure Python — no dependency)
# ---------------------------------------------------------------------------


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens. Deterministic and dependency-free."""
    return _WORD.findall((text or "").lower())


def lcs_length(a: list, b: list) -> int:
    """Length of the longest common SUBSEQUENCE of two sequences.

    Classic dynamic program, O(len(a)*len(b)) time, O(len(b)) space (one rolling
    row). 'Subsequence' (order-preserving, gaps allowed) — not 'substring' — is
    what makes ROUGE-L reward correct ordering without demanding adjacency.
    """
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        curr = [0] * (len(b) + 1)
        for j, y in enumerate(b, start=1):
            curr[j] = prev[j - 1] + 1 if x == y else max(prev[j], curr[j - 1])
        prev = curr
    return prev[-1]


def rouge_l(candidate: str, reference: str) -> dict:
    """ROUGE-L precision / recall / F1 over word tokens.

        precision = LCS / len(candidate tokens)   — how much of the candidate is on-reference
        recall    = LCS / len(reference tokens)   — how much of the reference the candidate covers
        f1        = harmonic mean of the two       — 0 when either side is empty
    """
    cand = tokenize(candidate)
    ref = tokenize(reference)
    if not cand or not ref:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0,
                "lcs": 0, "cand_len": len(cand), "ref_len": len(ref)}
    lcs = lcs_length(cand, ref)
    precision = lcs / len(cand)
    recall = lcs / len(ref)
    f1 = 0.0 if (precision + recall) == 0 else (
        2 * precision * recall / (precision + recall))
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "lcs": lcs,
            "cand_len": len(cand), "ref_len": len(ref)}


def bert_score_f1(candidates: list[str], references: list[str],
                  lang: str = "en") -> list[float]:
    """Optional SEMANTIC metric (BERTScore F1 per pair).

    Lazily imports bert_score — it pulls a ~1.4 GB transformer model on first
    use (network required), so this is never called unless --bertscore is set.
    Where ROUGE-L counts exact-word overlap, BERTScore measures embedding
    similarity, so a faithful paraphrase can score high here but low on ROUGE-L.
    """
    from bert_score import score as _score  # heavy + network on first run

    _, _, f1 = _score(candidates, references, lang=lang, verbose=False)
    return [round(float(x), 4) for x in f1]


# ---------------------------------------------------------------------------
# Scoring a results file against its suite's references
# ---------------------------------------------------------------------------


def load_references(suite_version: str) -> dict[str, str]:
    """question_id -> reference, parsed from tasks/<suite_version>.jsonl.

    The metadata line (no 'id') is skipped; only rows carrying both an id and a
    reference are kept."""
    path = TASKS_DIR / f"{suite_version}.jsonl"
    refs: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if "id" in row and "reference" in row:
                refs[row["id"]] = row["reference"]
    return refs


def score_results_file(results_path: Path, suite_version: str | None = None,
                       with_bertscore: bool = False) -> dict:
    """ROUGE-L per question for a results JSONL, joined to suite references.

    Rows whose question_id isn't in the suite are skipped. The candidate text is
    the row's ``candidate_response``; the judge's ``overall`` is carried along so
    the two metrics can be compared side by side.
    """
    rows = [json.loads(line) for line in
            results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return {"results_file": results_path.name, "n": 0, "rows": []}

    if suite_version is None:
        suite_version = rows[0].get("adaptation", {}).get("task_suite_version", "")
    refs = load_references(suite_version)

    # (qid, candidate, reference, judge_overall) for rows that join to the suite
    pairs = [
        (r.get("question_id"), r.get("candidate_response", ""),
         refs[r["question_id"]], r.get("overall"))
        for r in rows
        if r.get("question_id") in refs
    ]

    scored = []
    for qid, cand, ref, judge in pairs:
        m = rouge_l(cand, ref)
        scored.append({"question_id": qid, "rouge_l_f1": m["f1"],
                       "precision": m["precision"], "recall": m["recall"],
                       "candidate_empty": not (cand or "").strip(),
                       "judge_overall": judge})

    if with_bertscore and pairs:
        for s, b in zip(scored, bert_score_f1([c for _, c, _, _ in pairs],
                                              [r for _, _, r, _ in pairs])):
            s["bertscore_f1"] = b

    f1s = [s["rouge_l_f1"] for s in scored]
    out = {
        "results_file": results_path.name,
        "suite_version": suite_version,
        "candidate_model": rows[0].get("adaptation", {}).get("candidate_model", ""),
        "n": len(scored),
        "mean_rouge_l_f1": round(statistics.mean(f1s), 4) if f1s else 0.0,
        "rows": scored,
    }
    if with_bertscore and scored:
        out["mean_bertscore_f1"] = round(
            statistics.mean(s["bertscore_f1"] for s in scored), 4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ROUGE-L (+ optional BERTScore) for a results JSONL.")
    ap.add_argument("--results", type=Path, required=True,
                    help="path to a results JSONL written by runner.py")
    ap.add_argument("--suite", default=None,
                    help="suite version override (default: read from the run)")
    ap.add_argument("--bertscore", action="store_true",
                    help="also compute BERTScore (downloads a ~1.4GB model)")
    args = ap.parse_args()

    out = score_results_file(args.results, args.suite, args.bertscore)
    print(f"{out['results_file']}  model={out.get('candidate_model', '')}  "
          f"suite={out.get('suite_version', '')}  n={out['n']}")
    print(f"  mean ROUGE-L F1: {out['mean_rouge_l_f1']}")
    if "mean_bertscore_f1" in out:
        print(f"  mean BERTScore F1: {out['mean_bertscore_f1']}")
    print(f"  {'question':<10}{'rougeL_f1':>10}{'judge':>8}")
    for s in out["rows"]:
        flag = "  (empty candidate)" if s["candidate_empty"] else ""
        print(f"  {s['question_id']:<10}{s['rouge_l_f1']:>10}"
              f"{str(s['judge_overall']):>8}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
