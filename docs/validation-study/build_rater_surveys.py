"""
build_rater_surveys.py — the SELF-LABEL survey design (6-rater trio, 60 items).

Supersedes the 12-team disjoint design (build_versions.py) for the case the Code+
team chose: **the team labels it themselves — 6 committed raters, 30 questions
each (~25 min), every question labeled by exactly 3 people.**

Design — COMPLEMENTARY-partition blocks (no rater sees a prompt twice):
  * Item pool  = the frozen 108 comparisons in item_pool.jsonl (54 prompts × 2
                 opponents; every comparison includes the DPO target Qwen2.5-7B).
  * Selection  = a balanced **60** — 5 prompts per task type × both opponents, via
                 round-robin over task types (30 Mini + 30 Nano).
  * Redundancy = **3 labels per item** (odd → clean majority for Fleiss' κ).
  * Raters     = **6**. Each prompt's TWO opponent-comparisons (vs Mini, vs Nano)
                 go to the two COMPLEMENTARY halves of the raters — 3 label one,
                 the other 3 label the other. There are 10 such partitions, 3
                 prompts each. Every item still gets 3 labels and every rater does
                 exactly 30 — but **no rater ever sees the same prompt twice**
                 (each sees all 30 prompts once, one opponent apiece). Fixing an
                 earlier trio design where a rater could get both opponents of a
                 prompt back-to-back (the identical target answer, order flipped).
  * Order      = task types round-robin'd within each survey; A/B display order
                 counterbalanced by slot parity, and an item lands at different
                 slots across its 3 raters, so order is decorrelated from the item.

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


def complementary_partitions(
    n_raters: int = N_RATERS,
) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    """The 10 ways to split the 6 raters into two complementary trios
    (half_a, half_b). Rater 0 is always in half_a (a fixed canonical order)."""
    full = set(range(n_raters))
    parts = []
    for trio in combinations(range(n_raters), n_raters // 2):
        if 0 in trio:
            parts.append((trio, tuple(sorted(full - set(trio)))))
    return parts


def _mix_order(items: list[dict]) -> list[dict]:
    """Round-robin by task type so a rater's survey isn't all-email-then-all-plain."""
    by_type: "OrderedDict[str, list[dict]]" = OrderedDict()
    for it in items:
        by_type.setdefault(it["task_type"], []).append(it)
    queues = [list(v) for v in by_type.values()]
    out: list[dict] = []
    while queues:
        for q in queues:
            out.append(q.pop(0))
        queues = [q for q in queues if q]
    return out


def assign(
    items: list[dict],
    partitions: list[tuple[tuple[int, ...], tuple[int, ...]]] | None = None,
) -> tuple[dict, dict]:
    """Assign each PROMPT's two opponent-comparisons to the two COMPLEMENTARY
    halves of a rater partition, so **no rater ever sees the same prompt twice**.

    A prompt contributes 2 items (vs Mini, vs Nano); 3 raters label one, the
    complementary 3 label the other. 10 partitions × 3 prompts. Every item still
    gets 3 labels and every rater still does 30 — but each rater now sees 30
    DISTINCT prompts (one opponent apiece). Returns (rater -> [items], task-type
    mixed; item_id -> the trio of 3 raters who label it)."""
    if partitions is None:
        partitions = complementary_partitions(N_RATERS)
    by_prompt: "OrderedDict[str, list[dict]]" = OrderedDict()
    for it in items:
        by_prompt.setdefault(it["source"], []).append(it)
    prompts = list(by_prompt.values())               # each is [item_mini, item_nano]
    per_part = len(prompts) // len(partitions)        # 30 // 10 = 3

    rater_items: dict[int, list[dict]] = {r: [] for r in range(N_RATERS)}
    item_trio: dict[str, tuple[int, ...]] = {}
    for j, pair in enumerate(prompts):
        half_a, half_b = partitions[j // per_part]
        # alternate which opponent goes to half_a so each rater gets a Mini/Nano mix
        a_item, b_item = (pair[0], pair[1]) if j % 2 == 0 else (pair[1], pair[0])
        item_trio[a_item["item_id"]] = half_a
        item_trio[b_item["item_id"]] = half_b
        for r in half_a:
            rater_items[r].append(a_item)
        for r in half_b:
            rater_items[r].append(b_item)
    return {r: _mix_order(v) for r, v in rater_items.items()}, item_trio


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
                f"<br>"                                    # line between the task and Response 1
                f"<p><strong>Response 1</strong><br>{_q(_resp_plain(resp, it['source'], r1))}</p>"
                f"<br>"                                    # line between the two responses
                f"<p><strong>Response 2</strong><br>{_q(_resp_plain(resp, it['source'], r2))}</p>"
                f"<br>"                                    # line between Response 2 and the question
                f"<p><strong>Which answer is better?</strong></p><hr>")
        out += ["[[Question:MC:SingleAnswer]]", f"[[ID:{qid}]]", body,
                "[[Choices]]", "Response 1", "Response 2", "About the same", "",
                "[[PageBreak]]", ""]
    return "\n".join(out) + "\n"


def main() -> int:
    pool = load_pool()
    items = select_items(pool)
    rater_items, item_trio = assign(items)
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
          f"each comparison labeled by exactly **{LABELS_PER_ITEM}** raters → clean "
          "odd majority for Fleiss' κ.",
          "- A prompt's two opponent-comparisons go to **complementary halves** of "
          "the raters, so **no rater ever sees the same prompt twice** (each sees "
          "all 30 prompts once, one opponent apiece).",
          f"- Judge = {JUDGE} (cross-family). Task types round-robin'd; A/B order "
          "counterbalanced within each survey.",
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
    each_item_3 = all(len(t) == LABELS_PER_ITEM for t in item_trio.values())
    max_dupe = max(
        max(Counter(it["source"] for it in rater_items[r]).values())
        for r in range(N_RATERS)
    )
    opp_bal = {r: dict(Counter(it["opponent_model"] for it in rater_items[r]))
               for r in range(N_RATERS)}
    print(f"selected {len(items)} items ({dict(by_opp)}), "
          f"{len(complementary_partitions())} complementary partitions")
    print(f"questions per rater: {per_rater}")
    print(f"every item has exactly {LABELS_PER_ITEM} labels: {each_item_3}")
    print(f"max times any rater sees one prompt: {max_dupe} (must be 1)")
    print(f"opponent split per rater: {opp_bal}")
    print(f"total labels: {sum(per_rater.values())} (= {len(items)} items × {LABELS_PER_ITEM})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
