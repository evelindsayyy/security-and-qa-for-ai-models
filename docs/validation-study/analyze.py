"""
analyze.py — turn the 6 rater surveys into the study's numbers.

Pipeline (analysis_plan.md Steps A–F), built on prefstats.py (pure numpy):

  survey CSVs + rater_map.csv ─▶ undo display order ─▶ per-item human prefs
    A  consensus per item (2/3 majority; ties/splits → no_consensus)
    B  human–human agreement (Fleiss' κ — exactly 3 raters/item)   ← THE GATE
    C  judge vs human consensus (Cohen's κ + % agreement)          ← headline
    D  bias probes (position P(R1); length longer-won-rate)
    E  Bradley-Terry ranking of the 3 systems from the preferences
    F  DPO export → dpo_pairs.jsonl  (prompt, chosen, rejected)

The join + every aggregate is a pure function (unit-tested on synthetic labels in
test_analyze.py) so the pipeline is verified before real ratings arrive. main()
runs it on whatever rater CSVs are present; with none, it says so and stops.

Survey CSVs: export each rater's Qualtrics responses to CSV and save as
``<responses-dir>/rater_0X.csv`` (the rater number in the filename is the join
key). Judge prefs (Step C) are read from ``judge_prefs.jsonl`` when present.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import prefstats as ps

HERE = Path(__file__).resolve().parent

# The 3 systems being compared (Qwen is the DPO target, in every comparison).
SYSTEMS = ["Qwen2.5-7B-Instruct", "GPT 4.1 Mini", "GPT 4.1 Nano"]
CHOICE_MAP = {"Response 1": "R1", "Response 2": "R2", "About the same": ps.TIE}


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_item_pool(path: Path = HERE / "item_pool.jsonl") -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            it = json.loads(line)
            out[it["item_id"]] = it
    return out


def load_responses(path: Path = HERE / "responses.jsonl") -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["source"], r["model"])] = r["text"]
    return out


def load_rater_map(path: Path = HERE / "rater_map.csv") -> dict:
    out = {}
    for row in csv.DictReader(path.open(encoding="utf-8")):
        out[(row["rater"], row["item_id"])] = {
            "slot": int(row["slot"]),
            "r1": row["response1_model"],
            "r2": row["response2_model"],
        }
    return out


def parse_qualtrics_csv(text: str, rater: str) -> list[tuple[str, str, str]]:
    """One rater's Qualtrics export → (rater, item_id, choice) labels.

    Qualtrics puts the export tags on header row 1 (question IDs like ``itm_001``),
    then two metadata rows (question text + an importId JSON), then one data row
    per response. We map the answer text back to R1/R2/tie and the underscore id
    back to a hyphen id."""
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return []
    header = rows[0]
    item_cols = {i: h.strip().replace("_", "-")
                 for i, h in enumerate(header) if h.strip().startswith("itm_")}
    # skip the 2 Qualtrics metadata rows when present
    data_rows = rows[3:] if len(rows) > 3 else rows[1:]
    labels: list[tuple[str, str, str]] = []
    for row in data_rows:
        if not any(cell.strip() for cell in row):
            continue
        for i, item_id in item_cols.items():
            if i < len(row):
                choice = CHOICE_MAP.get(row[i].strip())
                if choice:
                    labels.append((rater, item_id, choice))
    return labels


def _rater_from_filename(stem: str) -> str:
    m = re.search(r"(\d{2})", stem)
    return m.group(1) if m else stem


def load_labels_from_dir(responses_dir: Path) -> list[tuple[str, str, str]]:
    labels: list[tuple[str, str, str]] = []
    for f in sorted(responses_dir.glob("rater_*.csv")):
        labels += parse_qualtrics_csv(f.read_text(encoding="utf-8"),
                                      _rater_from_filename(f.stem))
    return labels


def load_judge_prefs(path: Path = HERE / "judge_prefs.jsonl") -> dict[str, str]:
    """Optional Step-C input: {"item_id","judge_pref"} per line (judge_pref is a
    system id or 'tie'). Produced later by the pairwise-judge run."""
    out: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[r["item_id"]] = r["judge_pref"]
    return out


# ---------------------------------------------------------------------------
# Join + aggregates (pure — unit-tested)
# ---------------------------------------------------------------------------


def human_prefs_by_item(labels, rater_map) -> dict[str, list[str]]:
    """Undo display order per label → {item_id: [system_pref, ...]}."""
    by_item: dict[str, list[str]] = defaultdict(list)
    for rater, item_id, choice in labels:
        m = rater_map.get((rater, item_id))
        if m is not None:
            by_item[item_id].append(ps.to_system_pref(choice, m["r1"], m["r2"]))
    return dict(by_item)


def consensus_by_item(prefs_by_item) -> dict[str, str]:
    return {iid: ps.consensus(prefs) for iid, prefs in prefs_by_item.items()}


def human_human_kappa(prefs_by_item, expected: int = 3) -> Optional[float]:
    """Fleiss' κ over items that have the full complement of labels."""
    rows = [p for p in prefs_by_item.values() if len(p) == expected]
    if len(rows) < 2:
        return None
    table = ps.labels_to_fleiss_table(rows, categories=SYSTEMS + [ps.TIE])
    return ps.fleiss_kappa(table)


def judge_vs_human(consensus, judge_pref) -> dict:
    """Cohen's κ + % agreement of the judge against human consensus, over items
    that have a consensus AND a judge label."""
    items = [i for i, c in consensus.items() if c != ps.NO_CONSENSUS and i in judge_pref]
    if not items:
        return {"n": 0, "kappa": None, "pct": None}
    h = [consensus[i] for i in items]
    j = [judge_pref[i] for i in items]
    pct = sum(1 for a, b in zip(h, j) if a == b) / len(items)
    return {"n": len(items), "kappa": ps.cohen_kappa(h, j), "pct": pct}


def position_bias_human(labels) -> Optional[float]:
    """P(pick Response 1) among non-tie human labels. ~0.5 = unbiased."""
    non_tie = [c for _, _, c in labels if c in ("R1", "R2")]
    if not non_tie:
        return None
    return sum(1 for c in non_tie if c == "R1") / len(non_tie)


def _winner_loser(item: dict, winner_model: str) -> tuple[str, str]:
    loser = item["opponent_model"] if winner_model == item["target_model"] else item["target_model"]
    return winner_model, loser


def length_bias(consensus, item_pool, responses) -> dict:
    """Did the longer answer win? longer_won_rate (~0.5 = no bias) + point-biserial
    r(is_longer, was_chosen) over the two responses of each decided item."""
    longer_won: list[int] = []
    is_longer: list[float] = []
    was_chosen: list[float] = []
    for iid, c in consensus.items():
        if c in (ps.NO_CONSENSUS, ps.TIE):
            continue
        it = item_pool.get(iid)
        if it is None:
            continue
        win, lose = _winner_loser(it, c)
        wt, lt = responses.get((it["source"], win)), responses.get((it["source"], lose))
        if wt is None or lt is None:
            continue
        longer_won.append(1 if len(wt) > len(lt) else 0)
        is_longer += [1.0 if len(wt) > len(lt) else 0.0, 1.0 if len(lt) > len(wt) else 0.0]
        was_chosen += [1.0, 0.0]                       # winner then loser
    rate = sum(longer_won) / len(longer_won) if longer_won else None
    r = ps.point_biserial(is_longer, was_chosen) if longer_won else None
    return {"n": len(longer_won), "longer_won_rate": rate, "point_biserial": r}


def bradley_terry_ranking(consensus, item_pool):
    pairs = []
    for iid, c in consensus.items():
        if c in (ps.NO_CONSENSUS, ps.TIE):
            continue
        it = item_pool.get(iid)
        if it is not None:
            pairs.append(_winner_loser(it, c))         # (winner, loser)
    return ps.bradley_terry_ranking(SYSTEMS, pairs)


def dpo_triples(consensus, item_pool, responses) -> list[dict]:
    out = []
    for iid, c in consensus.items():
        if c in (ps.NO_CONSENSUS, ps.TIE):
            continue
        it = item_pool.get(iid)
        if it is None:
            continue
        chosen, rejected = _winner_loser(it, c)
        ct = responses.get((it["source"], chosen))
        rt = responses.get((it["source"], rejected))
        if ct is not None and rt is not None:
            out.append({"prompt": it["prompt"], "chosen": ct, "rejected": rt})
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def analyze(labels, rater_map, item_pool, responses, judge_pref) -> dict:
    prefs = human_prefs_by_item(labels, rater_map)
    cons = consensus_by_item(prefs)
    decided = {i: c for i, c in cons.items() if c not in (ps.NO_CONSENSUS, ps.TIE)}
    return {
        "n_items": len(prefs),
        "n_labels": len(labels),
        "no_consensus": sum(1 for c in cons.values() if c == ps.NO_CONSENSUS),
        "human_kappa": human_human_kappa(prefs),
        "judge": judge_vs_human(cons, judge_pref),
        "position_p_r1": position_bias_human(labels),
        "length": length_bias(cons, item_pool, responses),
        "ranking": bradley_terry_ranking(cons, item_pool),
        "dpo": dpo_triples(cons, item_pool, responses),
        "consensus": cons,
        "n_decided": len(decided),
    }


def _fmt(x, nd=3):
    return "—" if x is None else f"{x:.{nd}f}"


def print_report(res: dict) -> None:
    print(f"\nRater labels: {res['n_labels']}  ·  items with labels: {res['n_items']}"
          f"  ·  no-consensus: {res['no_consensus']}  ·  decided: {res['n_decided']}")
    hk = res["human_kappa"]
    print(f"\n[B] Human–human agreement (Fleiss' κ): {_fmt(hk)}"
          + (f"  ({ps.kappa_reading(hk)})" if hk is not None else "")
          + "   ← the ceiling / gate (≥0.40)")
    jd = res["judge"]
    if jd["n"]:
        print(f"[C] Judge vs human (Cohen's κ): {_fmt(jd['kappa'])}"
              f"  ({ps.kappa_reading(jd['kappa'])})  ·  % agreement: {_fmt(jd['pct'])}"
              f"  (n={jd['n']})   ← headline")
    else:
        print("[C] Judge vs human: (no judge_prefs.jsonl yet — run the pairwise judge)")
    print(f"[D] Position bias P(R1): {_fmt(res['position_p_r1'])}  (~0.5 unbiased)")
    lb = res["length"]
    print(f"    Length bias: longer won {_fmt(lb['longer_won_rate'])} of "
          f"{lb['n']} decided  ·  point-biserial r={_fmt(lb['point_biserial'])}")
    print("[E] Bradley-Terry ranking:")
    for s, v in res["ranking"]:
        print(f"      {s:24} θ={v:+.3f}")
    print(f"[F] DPO pairs: {len(res['dpo'])}")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Analyze the rater surveys.")
    p.add_argument("--responses-dir", type=Path, default=HERE / "responses_csv",
                   help="dir of rater_0X.csv Qualtrics exports")
    p.add_argument("--dpo-out", type=Path, default=HERE / "dpo_pairs.jsonl")
    args = p.parse_args(argv)

    item_pool = load_item_pool()
    responses = load_responses()
    rater_map = load_rater_map()
    judge_pref = load_judge_prefs()

    if not args.responses_dir.is_dir() or not list(args.responses_dir.glob("rater_*.csv")):
        print(f"No rater CSVs in {args.responses_dir} yet. Export each rater's "
              "Qualtrics responses to CSV as rater_0X.csv there, then re-run.")
        return 0

    labels = load_labels_from_dir(args.responses_dir)
    res = analyze(labels, rater_map, item_pool, responses, judge_pref)
    print_report(res)

    with args.dpo_out.open("w", encoding="utf-8") as f:
        for t in res["dpo"]:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"\nWrote {len(res['dpo'])} DPO pairs → {args.dpo_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
