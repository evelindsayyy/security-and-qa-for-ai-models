"""
robustness.py — perturbation generation + robustness scoring (HELM's 3rd bucket).

Robustness asks: does a model's quality hold up when a real user phrases the
same question imperfectly? We take a base question, make perturbed variants, run
BOTH through the normal pipeline, and compare the scores. Per metrics.yaml, this
is a COMPARISON computed after the fact from paired result rows — high accuracy
on clean prompts does NOT imply robustness.

Two halves:

  1. `typo(...)` — a mechanical, seeded (reproducible) perturbation: lowercase,
     drop terminal punctuation, abbreviate common words, add the odd char-level
     typo. The `informal` and `ambiguous` perturbation types are semantic
     rewrites (see metrics.yaml's examples) and are HAND-AUTHORED in the
     robustness suite, not mechanically generated.

  2. `robustness_report(...)` — pairs each base question's original score with
     its perturbed variants' scores and computes score_drop / robustness_ratio /
     pass_rate_drop, per perturbation type and overall.

Standalone post-processing, run after a robustness-suite results file exists:

    python -m evaluator.robustness --results results/<run>.jsonl [--suite robustness_v1]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "tasks"

# Canonical taxonomy — mirrors metrics.yaml's robustness.perturbation_types.
PERTURBATION_TYPES = ("typo", "informal", "ambiguous")
# A response scoring >= this counts as "passed" (metrics.yaml pass_rate_drop).
PASS_THRESHOLD = 4.0

# Common words a casual user abbreviates. Applied before the char-level typo.
_ABBREV = {
    "password": "pwd", "please": "pls", "account": "acct", "message": "msg",
    "number": "num", "information": "info", "because": "cuz", "tomorrow": "tmrw",
    "you": "u", "your": "ur", "are": "r", "before": "b4",
}


# ---------------------------------------------------------------------------
# Perturbation generation (mechanical types only)
# ---------------------------------------------------------------------------


def _mangle(word: str, rng: random.Random) -> str:
    """Introduce one small char-level typo: swap / drop / double a character."""
    if len(word) < 2:
        return word
    i = rng.randrange(len(word) - 1)
    kind = rng.choice(("swap", "drop", "double"))
    if kind == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if kind == "drop":
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]  # double the char


def typo(text: str, seed: int = 0) -> str:
    """Mechanical 'typos + casual capitalization' perturbation (deterministic
    for a given seed): lowercase, drop terminal punctuation, abbreviate a few
    common words, and occasionally add a single char-level typo. Reproducible so
    the frozen robustness suite regenerates identically.

    Example: "How do I reset my Duke NetID password?" -> "how do i reset my duke
    netid pwd" (plus the occasional char slip)."""
    rng = random.Random(seed)
    t = (text or "").strip().rstrip("?.!").lower()
    out = []
    for w in t.split():
        if w in _ABBREV:
            out.append(_ABBREV[w])
        elif len(w) > 3 and rng.random() < 0.30:
            out.append(_mangle(w, rng))
        else:
            out.append(w)
    return " ".join(out)


# ---------------------------------------------------------------------------
# Robustness scoring (paired comparison)
# ---------------------------------------------------------------------------


def suite_id_meta(suite_version: str) -> dict[str, dict]:
    """question_id -> {base_id, perturbation} from a robustness suite's rows."""
    path = TASKS_DIR / f"{suite_version}.jsonl"
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if "id" in row and "base_id" in row:
            out[row["id"]] = {
                "base_id": row["base_id"],
                "perturbation": row.get("perturbation", "original"),
            }
    return out


def _metrics(pairs: list[tuple[float, float]]) -> dict:
    """score_drop / robustness_ratio / pass_rate_drop for a list of
    (original_score, perturbed_score) pairs. Empty -> {n: 0}."""
    if not pairs:
        return {"n": 0}
    orig = [o for o, _ in pairs]
    pert = [p for _, p in pairs]
    mo, mp = statistics.mean(orig), statistics.mean(pert)
    dropped = sum(1 for o, p in pairs
                  if o >= PASS_THRESHOLD and p < PASS_THRESHOLD)
    # Exact floats kept in the report (consumers round as needed); the CLI
    # rounds only for display.
    return {
        "n": len(pairs),
        "mean_original": mo,
        "mean_perturbed": mp,
        "score_drop": mp - mo,                          # negative = degraded
        "robustness_ratio": (mp / mo) if mo else None,
        "pass_rate_drop": dropped / len(pairs),
    }


def robustness_report(rows: list[dict], id_to_meta: dict[str, dict]) -> dict:
    """Pair original vs perturbed result rows and compute the robustness metrics.

    `rows` carry at least question_id + overall; `id_to_meta` maps question_id ->
    {base_id, perturbation}. For each base question we line up its original score
    against each perturbed variant, then aggregate per perturbation type and
    overall. Rows with no overall (or no suite mapping) are ignored.
    """
    by_base: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        meta = id_to_meta.get(r.get("question_id"))
        if not meta:
            continue
        ov = r.get("overall")
        if ov is None:
            continue
        by_base[meta["base_id"]][meta["perturbation"]] = float(ov)

    ptypes = sorted({m["perturbation"] for m in id_to_meta.values()
                     if m["perturbation"] != "original"})

    by_perturbation: dict[str, dict] = {}
    all_pairs: list[tuple[float, float]] = []
    for pt in ptypes:
        pairs = [(v["original"], v[pt]) for v in by_base.values()
                 if "original" in v and pt in v]
        by_perturbation[pt] = _metrics(pairs)
        all_pairs.extend(pairs)

    return {
        "by_perturbation": by_perturbation,
        "overall": _metrics(all_pairs),
        "pass_threshold": PASS_THRESHOLD,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Robustness score-drop from a robustness-suite results JSONL.")
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--suite", default=None,
                    help="robustness suite version (default: read from the run)")
    args = ap.parse_args()

    rows = [json.loads(line) for line in
            args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    suite = args.suite or (
        rows[0].get("adaptation", {}).get("task_suite_version", "") if rows else "")
    rep = robustness_report(rows, suite_id_meta(suite))

    def _fmt(m: dict) -> str:
        ratio = m["robustness_ratio"]
        ratio_s = f"{ratio:.3f}" if ratio is not None else "n/a"
        return (f"n={m['n']}  drop={m['score_drop']:+.2f}  "
                f"ratio={ratio_s}  pass_drop={m['pass_rate_drop']:.2f}")

    print(f"robustness · suite={suite}  (pass >= {rep['pass_threshold']})")
    for pt, m in rep["by_perturbation"].items():
        if m["n"]:
            print(f"  {pt:10} {_fmt(m)}")
    if rep["overall"]["n"]:
        print(f"  {'OVERALL':10} {_fmt(rep['overall'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
