"""
build_rater_surveys.py — the SELF-LABEL survey design (6-rater trio, 60 items).

Supersedes the 12-team disjoint design (build_versions.py) for the case the Code+
team chose: **the team labels it themselves — 6 committed raters, 30 questions
each (~25 min), every question labeled by exactly 3 people.**

Design — OVERLAPPING trio blocks:
  * Item pool  = the frozen 108 comparisons in item_pool.jsonl (54 prompts × 2
                 opponents; every comparison includes the DPO target Qwen2.5-7B).
  * Selection  = a balanced **60** — 5 prompts per task type × both opponents, via
                 round-robin over task types (30 Mini + 30 Nano).
  * Redundancy = **3 labels per item** (odd → clean majority for Fleiss' κ).
  * Raters     = **6**. There are exactly C(6,3)=20 trios; each of the 60 items is
                 assigned to one trio (3 items per trio). Each rater sits in
                 C(5,2)=10 trios → rates exactly 30 items. Perfectly balanced:
                 every item gets 3 labels, every rater does 30.
  * Order      = A/B display order counterbalanced within each rater's survey
                 (slot parity); the same item lands at different slots across its
                 3 raters, so order is decorrelated from the item (position-bias
                 probe stays clean).

Deterministic (no randomness) → reproducible + reviewable. Reads the already-
generated item_pool.jsonl + responses.jsonl; does NOT touch build_versions.py or
its outputs.

Outputs (docs/validation-study/):
  rater_map.csv   rater, item_id, task_type, slot, response1_model, response2_model
  rater_map.md    design summary + per-rater item lists + coverage
  rater_01.md ..  one rendered survey per rater (6)
  qualtrics_rater_01.txt ..  one Qualtrics Advanced-Format import per rater (6)
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter, OrderedDict
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent

N_RATERS = 6
LABELS_PER_ITEM = 3                       # each comparison → a trio of 3 raters
QUESTIONS_PER_RATER = 30
N_ITEMS = N_RATERS * QUESTIONS_PER_RATER // LABELS_PER_ITEM   # 6*30/3 = 60

DPO_TARGET = "Qwen2.5-7B-Instruct"
OPPONENTS = ["GPT 4.1 Mini", "GPT 4.1 Nano"]
JUDGE = "Llama 4 Maverick"

FORM_TITLE = "Which AI Answer Is Better? (~25 min)"
FORM_DESCRIPTION = (
    "Thanks for helping out! In each question, an AI was asked to do a small task — "
    "write an email, explain an idea, or rewrite a notice — and you'll see two AI "
    "answers to the same task. Just pick the one you think is better (clearer, more "
    "correct, or more helpful), or choose \"About the same\" if they're equally good. "
    "There are no right answers and you don't need any special background — go with "
    "your honest first impression. It takes about 25 minutes (feel free to do it in "
    "two sittings). Your picks help us check how well an automated AI grader matches "
    "real people's judgment. Thank you!"
)

TASK_BLURB = {
    "email": "draft an email", "plain": "rewrite something in plain language",
    "tutoring": "help a confused student", "summarization": "summarize a passage",
    "it_support": "answer an IT question", "policy_qa": "answer a Duke policy question",
}


# ---------------------------------------------------------------------------
# Pure allocation (unit-tested) — no file writes here.
# ---------------------------------------------------------------------------


def load_pool() -> list[dict]:
    return [json.loads(line)
            for line in (HERE / "item_pool.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()]


def select_items(pool: list[dict], n_items: int = N_ITEMS) -> list[dict]:
    """A balanced n_items subset: round-robin over task types picking prompts
    one-per-type in rotation, then include BOTH opponent items for each prompt.

    Round-robin keeps the task-type mix even and the opponent split exactly 50/50
    (each picked prompt contributes one Mini + one Nano item)."""
    seen: set[str] = set()
    by_type: "OrderedDict[str, list[str]]" = OrderedDict()
    for it in pool:                       # unique prompts (source) in pool order
        if it["source"] not in seen:
            seen.add(it["source"])
            by_type.setdefault(it["task_type"], []).append(it["source"])

    need_prompts = n_items // 2
    idx = {tt: 0 for tt in by_type}
    picked: list[str] = []
    types = list(by_type)
    while len(picked) < need_prompts:
        advanced = False
        for tt in types:
            if len(picked) >= need_prompts:
                break
            if idx[tt] < len(by_type[tt]):
                picked.append(by_type[tt][idx[tt]])
                idx[tt] += 1
                advanced = True
        if not advanced:                  # ran out of prompts (shouldn't happen)
            break

    picked_set = set(picked)
    return [it for it in pool if it["source"] in picked_set]


def rater_trios(n_raters: int = N_RATERS) -> list[tuple[int, ...]]:
    """All C(n_raters, 3) trios, in a fixed deterministic order."""
    return [tuple(t) for t in combinations(range(n_raters), LABELS_PER_ITEM)]


def assign(items: list[dict], trios: list[tuple[int, ...]]) -> tuple[dict, dict]:
    """Assign each item to one trio (equal items per trio) and fan it out to that
    trio's 3 raters. Returns (rater -> [items], item_id -> trio)."""
    per_trio = len(items) // len(trios)
    rater_items: dict[int, list[dict]] = {r: [] for r in range(N_RATERS)}
    item_trio: dict[str, tuple[int, ...]] = {}
    for i, it in enumerate(items):
        trio = trios[i // per_trio]
        item_trio[it["item_id"]] = trio
        for r in trio:
            rater_items[r].append(it)
    return rater_items, item_trio


def display_models(it: dict, slot: int) -> tuple[str, str]:
    """Counterbalanced order: target model is Response 1 on even slots, 2 on odd."""
    t, o = it["target_model"], it["opponent_model"]
    return (t, o) if slot % 2 == 0 else (o, t)


# ---------------------------------------------------------------------------
# Rendering (only runs under __main__).
# ---------------------------------------------------------------------------


def load_responses() -> dict[tuple[str, str], str]:
    resp: dict[tuple[str, str], str] = {}
    p = HERE / "responses.jsonl"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                resp[(r["source"], r["model"])] = r["text"]
    return resp


def _resp_plain(resp, source: str, model: str) -> str:
    return resp.get((source, model), f"[{model} response — pending generation]")


def _resp_md(resp, source: str, model: str) -> str:
    txt = _resp_plain(resp, source, model)
    return "\n".join("> " + ln if ln else ">" for ln in txt.split("\n"))


def _q(text: str) -> str:
    """Model text -> clean HTML for Qualtrics (escape, render **bold**, tidy the
    rare LaTeX, newlines -> <br>, defuse [[ ]]). Mirrors build_versions._q."""
    t = html.escape(text, quote=False)
    t = re.sub(r"\\text\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    for a, b in ((r"\sum", "Σ"), (r"\times", "×"), (r"\cdot", "·"), (r"\div", "÷"),
                 (r"\left", ""), (r"\right", ""),
                 (r"\[", ""), (r"\]", ""), (r"\(", ""), (r"\)", "")):
        t = t.replace(a, b)
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return t.replace("\n", "<br>").replace("[[", "[ [").replace("]]", "] ]")


def rid(r: int) -> str:
    return f"{r + 1:02d}"


def render_markdown(r: int, items: list[dict], resp) -> str:
    lines = [f"# Rater {rid(r)} survey — {FORM_TITLE}", "",
             f"> Auto-generated by build_rater_surveys.py. One of {N_RATERS} rater "
             f"surveys; you answer these {len(items)} questions. Each question is also "
             f"answered by 2 other raters, so every question gets {LABELS_PER_ITEM} "
             "labels. Each item compares two AI models' answers to the same prompt.",
             "", "---", "",
             f"## {FORM_TITLE}", "", FORM_DESCRIPTION, "",
             "**Your name or email** (to thank you — not shared): `__________`",
             "", "---", ""]
    key = []
    for slot, it in enumerate(items):
        r1, r2 = display_models(it, slot)
        lines += [f"### Item {slot + 1} — the AI was asked to "
                  f"{TASK_BLURB[it['task_type']]}  ·  _{it['item_id']}_", "",
                  f"*{it['prompt']}*", "", "**Response 1**", _resp_md(resp, it["source"], r1), "",
                  "**Response 2**", _resp_md(resp, it["source"], r2), "",
                  "**Which is better?**  ◦ Response 1   ◦ Response 2   ◦ About the same",
                  "", "---", ""]
        key.append(f"| {it['item_id']} | {it['task_type']} | {r1} | {r2} |")
    lines += ["## Researcher key (NOT shown to raters)", "",
              "| item_id | task type | Response 1 model | Response 2 model |",
              "|---|---|---|---|", *key, "",
              "_The model behind each response is the join key for the DPO dataset. "
              "Order is counterbalanced by item for the position-bias analysis._"]
    return "\n".join(lines) + "\n"


def render_qualtrics(r: int, items: list[dict], resp) -> str:
    out = ["[[AdvancedFormat]]", "", f"[[Block:Rater {rid(r)}]]", "",
           "[[Question:DB]]", "[[ID:intro]]",
           f"<h3>{html.escape(FORM_TITLE, quote=False)}</h3>"
           f"<p>{html.escape(FORM_DESCRIPTION, quote=False)}</p>", "",
           "[[PageBreak]]", "",
           "[[Question:TE:SingleLine]]", "[[ID:rater]]",
           "Your name or email (so we can thank you — not shared):", "",
           "[[PageBreak]]", ""]
    for slot, it in enumerate(items):
        r1, r2 = display_models(it, slot)
        qid = it["item_id"].replace("-", "_")
        body = (f"<p><strong>Task:</strong> {_q(it['prompt'])}</p>"
                f"<p><strong>Response 1</strong><br>{_q(_resp_plain(resp, it['source'], r1))}</p>"
                f"<br>"
                f"<p><strong>Response 2</strong><br>{_q(_resp_plain(resp, it['source'], r2))}</p>"
                f"<p><strong>Which answer is better?</strong></p><hr>")
        out += ["[[Question:MC:SingleAnswer]]", f"[[ID:{qid}]]", body,
                "[[Choices]]", "Response 1", "Response 2", "About the same", "",
                "[[PageBreak]]", ""]
    return "\n".join(out) + "\n"


def main() -> int:
    pool = load_pool()
    items = select_items(pool)
    trios = rater_trios()
    rater_items, item_trio = assign(items, trios)
    resp = load_responses()

    # rater_map.csv — the per-rater join key (rater, item, order, models).
    csv_lines = ["rater,item_id,task_type,slot,response1_model,response2_model"]
    for r in range(N_RATERS):
        for slot, it in enumerate(rater_items[r]):
            r1, r2 = display_models(it, slot)
            csv_lines.append(f"{rid(r)},{it['item_id']},{it['task_type']},{slot + 1},{r1},{r2}")
    (HERE / "rater_map.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    for r in range(N_RATERS):
        (HERE / f"rater_{rid(r)}.md").write_text(
            render_markdown(r, rater_items[r], resp), encoding="utf-8")
        (HERE / f"qualtrics_rater_{rid(r)}.txt").write_text(
            render_qualtrics(r, rater_items[r], resp), encoding="utf-8")

    # rater_map.md — design summary.
    by_type = Counter(it["task_type"] for it in items)
    by_opp = Counter(it["opponent_model"] for it in items)
    md = ["# Rater survey design (self-label — 6 raters, 60 items, 3 labels each)", "",
          "> Auto-generated by `build_rater_surveys.py` (deterministic; re-run to regenerate).",
          "", "## Design", "",
          f"- **{len(items)} comparisons** selected from the 108-item pool "
          f"(item_pool.jsonl), balanced across task types.",
          "- Task-type mix: " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())) + ".",
          "- Opponent split: " + ", ".join(f"{k} {v}" for k, v in sorted(by_opp.items()))
          + f" (every comparison includes the DPO target {DPO_TARGET}).",
          f"- **{N_RATERS} raters**, **{QUESTIONS_PER_RATER} questions each** (~25 min); "
          f"each comparison labeled by exactly **{LABELS_PER_ITEM}** raters (a trio) → "
          "clean odd majority for Fleiss' κ.",
          f"- Judge = {JUDGE} (cross-family). Order counterbalanced within each survey.",
          "", "| rater | questions | rendered file | Qualtrics import |",
          "|---|---|---|---|"]
    for r in range(N_RATERS):
        md.append(f"| {rid(r)} | {len(rater_items[r])} | [rater_{rid(r)}.md](rater_{rid(r)}.md) "
                  f"| [qualtrics_rater_{rid(r)}.txt](qualtrics_rater_{rid(r)}.txt) |")
    md += ["", "## Per-rater item lists", ""]
    for r in range(N_RATERS):
        md.append(f"- **Rater {rid(r)}** — "
                  + ", ".join(it["item_id"] for it in rater_items[r]))
    (HERE / "rater_map.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    # invariants
    per_rater = {r: len(rater_items[r]) for r in range(N_RATERS)}
    labels = Counter()
    for trio in item_trio.values():
        for _r in trio:
            labels[_r] += 1
    each_item_3 = all(len(t) == LABELS_PER_ITEM for t in item_trio.values())
    print(f"selected {len(items)} items ({dict(by_opp)}), {len(trios)} trios")
    print(f"questions per rater: {per_rater}")
    print(f"every item has exactly {LABELS_PER_ITEM} labels: {each_item_3}")
    print(f"total labels: {sum(per_rater.values())} (= {len(items)} items × {LABELS_PER_ITEM})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
