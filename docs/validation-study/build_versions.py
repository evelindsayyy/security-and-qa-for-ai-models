"""
Build the judge-validation surveys from the REAL open-ended prompts in the suites.

Design — DISJOINT block design, MULTI-MODEL pairings (one survey per Code+ team):

  * Item pool  = every open-ended (judge-scored) prompt in tasks/*.jsonl, each
                 turned into pairwise comparisons between candidate models.
  * Models     = DPO_TARGET vs each OPPONENT. Every comparison includes the
                 DPO target (Qwen2.5-7B-Instruct) so the collected preferences are
                 ON-POLICY for the model we later DPO-train. The judge (Llama 4
                 Maverick, Meta) is a different family from all candidates.
  * Versions   = the items split into NON-OVERLAPPING blocks of ~QUESTIONS_PER_VERSION.
                 One survey per team; a prompt never repeats within a survey, and
                 no student sees a repeated prompt.
  * Raters     = the 3-5 students on a team all answer the same version, so every
                 question collects 3-5 labels.
  * Order      = A/B display order is counterbalanced (position-bias probe).

Real A/B responses are generated in W8 by running the two named models on each
prompt; here each response is a model-attributed placeholder. The join that turns
these + the human votes into DPO triples is in analysis_plan.md.

Deterministic (no randomness) so it is reproducible and reviewable.

Outputs (docs/validation-study/):
  item_pool.jsonl   item_id, task_type, prompt, target_model, opponent_model
  version_map.csv   item_id, task_type, version, slot, response1_model, response2_model
  version_map.md    design summary + per-version item lists
  version_01.md ..  one rendered survey per team
"""
from __future__ import annotations
import html
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = HERE.parent.parent / "evaluator" / "tasks"

QUESTIONS_PER_VERSION = 9       # target survey length (8-10)
TEAM_SIZE = "3-5"              # students per team = labels per question

FORM_TITLE = "Which AI Answer Is Better? (~10 min)"
FORM_DESCRIPTION = (
    "Thanks for helping out! In each question, an AI was asked to do a small task — "
    "write an email, explain an idea, or rewrite a notice — and you'll see two AI "
    "answers to the same task. Just pick the one you think is better (clearer, more "
    "correct, or more helpful), or choose \"About the same\" if they're equally good. "
    "There are no right answers and you don't need any special background — go with "
    "your honest first impression. It takes about 10 minutes. Your picks help us check "
    "how well an automated AI grader matches real people's judgment. Thank you!"
)

# Candidate models. DPO_TARGET is in EVERY comparison (on-policy for the DPO run).
# The 1.5B variant is a faster off-policy fallback for the PoC; the survey uses 7B.
DPO_TARGET = "Qwen2.5-7B-Instruct"          # served on the DCC (a5000, vLLM)
OPPONENTS = ["GPT 4.1 Mini", "GPT 4.1 Nano"]  # gateway calls (comparable + weaker)
JUDGE = "Llama 4 Maverick"      # cross-family: differs from all candidates

SUITES = {
    "email_drafting_v1": "email", "email_drafting_hard_v1": "email",
    "plain_language_v1": "plain", "plain_language_hard_v1": "plain",
    "tutoring_v1": "tutoring", "tutoring_hard_v1": "tutoring",
    "summarization_v1": "summarization",
    "it_support_v1": "it_support",
    "policy_qa_v1.1": "policy_qa",
}
TASK_BLURB = {
    "email": "draft an email", "plain": "rewrite something in plain language",
    "tutoring": "help a confused student", "summarization": "summarize a passage",
    "it_support": "answer an IT question", "policy_qa": "answer a Duke policy question",
}


# Anonymize personal names in the SURVEY only (the eval suites keep their wording).
# Fully generic lettered placeholders so no name can coincide with a real person.
# Applied to prompts before generation, so the W8 model responses use them too.
NAME_MAP = [
    ("Professor Lee", "Professor A"),
    ("Dr. Park", "Professor B"),
    ("Professor Nguyen", "Professor C"),
    ("teammate Sam", "teammate A"),
    ("teammate Jordan", "teammate B"),
]


def anonymize(text: str) -> str:
    for old, new in NAME_MAP:
        text = text.replace(old, new)
    return text


def load_suite(name: str) -> dict[str, dict]:
    rows = [json.loads(l) for l in (TASKS / f"{name}.jsonl").read_text().splitlines()
            if l.strip()]
    return {r["id"]: r for r in rows if "id" in r}


# ---- assemble prompts, then expand into model-pair comparison items ----------
prompts: list[dict] = []
for name, task_type in SUITES.items():
    for tid, row in load_suite(name).items():
        prompts.append({"task_type": task_type, "source": f"{name}:{tid}",
                        "prompt": anonymize(row["question"])})

pool: list[dict] = []           # one item per (prompt, opponent) -> includes DPO_TARGET
n = 0
for p_idx, p in enumerate(prompts):
    for j, opp in enumerate(OPPONENTS):
        n += 1
        pool.append({"item_id": f"itm-{n:03d}", "task_type": p["task_type"],
                     "source": p["source"], "prompt": p["prompt"],
                     "target_model": DPO_TARGET, "opponent_model": opp,
                     "_p": p_idx, "_j": j})

N = len(pool)                    # 54 prompts x 2 opponents = 108
NUM_VERSIONS = math.ceil(N / QUESTIONS_PER_VERSION)   # -> 12

# ---- disjoint assignment, opponent-BALANCED within each version --------------
# Offset each opponent by NUM_VERSIONS/len(OPPONENTS) so a version mixes opponents
# instead of clustering. (Plain round-robin with an even opponent count puts all
# of opponent A in the even versions and all of B in the odd ones.) A prompt's two
# items land in versions p and p+offset -> different versions, so no prompt repeats
# within a survey.
offset = max(1, NUM_VERSIONS // len(OPPONENTS))
versions: list[list[dict]] = [[] for _ in range(NUM_VERSIONS)]
for it in pool:
    versions[(it["_p"] + it["_j"] * offset) % NUM_VERSIONS].append(it)


def vid(v: int) -> str:
    return f"{v + 1:02d}"


def display_models(it: dict, slot: int) -> tuple[str, str]:
    """Counterbalanced order: target model is Response 1 on even slots, 2 on odd."""
    t, o = it["target_model"], it["opponent_model"]
    return (t, o) if slot % 2 == 0 else (o, t)


# ---- item_pool.jsonl ---------------------------------------------------------
(HERE / "item_pool.jsonl").write_text(
    "\n".join(json.dumps({"item_id": it["item_id"], "task_type": it["task_type"],
                          "source": it["source"], "prompt": it["prompt"],
                          "target_model": it["target_model"],
                          "opponent_model": it["opponent_model"]}, ensure_ascii=False)
              for it in pool) + "\n", encoding="utf-8")

# ---- version_map.csv (carries the model of each response -> the DPO join key) -
csv_lines = ["item_id,task_type,version,slot,response1_model,response2_model,labels_expected"]
for v, items in enumerate(versions):
    for slot, it in enumerate(items):
        r1, r2 = display_models(it, slot)
        csv_lines.append(f'{it["item_id"]},{it["task_type"]},{vid(v)},{slot+1},'
                         f'{r1},{r2},{TEAM_SIZE}')
(HERE / "version_map.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")


# ---- render each team survey -------------------------------------------------
# If responses.jsonl exists ({"item_id","model","text"}), fill the real text;
# otherwise show a placeholder. Re-running after W8 generation fills the surveys
# AND the Forms paste sheets automatically.
# Keyed by (prompt source, model): a model's answer to a prompt is the same
# across the items that share that prompt.
RESP: dict[tuple[str, str], str] = {}
_rp = HERE / "responses.jsonl"
if _rp.is_file():
    for _l in _rp.read_text(encoding="utf-8").splitlines():
        if _l.strip():
            _r = json.loads(_l)
            RESP[(_r["source"], _r["model"])] = _r["text"]


def resp_plain(source: str, model: str) -> str:
    return RESP.get((source, model), f"[{model} response — pending generation]")


def resp_md(source: str, model: str) -> str:
    txt = resp_plain(source, model)
    return "\n".join("> " + ln if ln else ">" for ln in txt.split("\n"))


for old in HERE.glob("version_[A-G].md"):    # stale files from earlier designs
    old.unlink()
for old in HERE.glob("version_0*.md"):
    old.unlink()

for v, items in enumerate(versions):
    lines = [f"# Survey Version {vid(v)} — {FORM_TITLE}", "",
             f"> Auto-generated by build_versions.py. One survey for one Code+ team "
             f"({TEAM_SIZE} students) — everyone answers these {len(items)} questions. "
             "No question appears in any other survey. Each item compares two AI "
             "models' answers to the same prompt.",
             "", "---", "",
             f"## {FORM_TITLE}", "", FORM_DESCRIPTION, "",
             "**Your name or email** (to thank you — not shared): `__________`",
             "", "---", ""]
    key = []
    for slot, it in enumerate(items):
        r1, r2 = display_models(it, slot)
        lines += [f"### Item {slot+1} — the AI was asked to "
                  f"{TASK_BLURB[it['task_type']]}  ·  _{it['item_id']}_", "",
                  f"*{it['prompt']}*", "", "**Response 1**", resp_md(it["source"], r1), "",
                  "**Response 2**", resp_md(it["source"], r2), "",
                  "**Which is better?**  ◦ Response 1   ◦ Response 2   ◦ About the same",
                  "", "---", ""]
        key.append(f"| {it['item_id']} | {it['task_type']} | {r1} | {r2} |")
    lines += ["## Researcher key (NOT shown to raters)", "",
              "| item_id | task type | Response 1 model | Response 2 model |",
              "|---|---|---|---|", *key, "",
              "_The model behind each response is the join key for the DPO dataset "
              "(a human pick → chosen/rejected model → chosen/rejected text). Order "
              "is counterbalanced by item for the position-bias analysis._"]
    (HERE / f"version_{vid(v)}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# ---- Qualtrics Advanced Format import files (one .txt per team) ---------------
# Importing one .txt builds the whole 9-question survey (Tools -> Import/Export ->
# Import Questions). See QUALTRICS_IMPORT.md.
for old in HERE.glob("forms_paste_*.txt"):       # remove superseded Microsoft Forms sheets
    old.unlink()


def _q(text: str) -> str:
    """Model text -> clean HTML for Qualtrics so it reads like a chat UI (not raw
    markup): escape HTML, render **bold**, tidy the rare LaTeX, newlines -> <br>,
    defuse [[ ]] (which would collide with the Advanced Format parser)."""
    t = html.escape(text, quote=False)
    # LaTeX -> readable. These commands are LaTeX-only (never in the code snippets),
    # so stripping them can't corrupt a code response. Order matters: dissolve the
    # nested {..} of subscripts/sums/text BEFORE \frac so its args become brace-free.
    t = re.sub(r"\\text\{([^{}]*)\}", r"\1", t)                     # \text{Mean} -> Mean
    t = re.sub(r"_\{([^{}]*)\}", r"_\1", t)                         # _{i=1} -> _i=1
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)                        # ^{n} -> ^n
    for a, b in ((r"\sum", "Σ"), (r"\times", "×"), (r"\cdot", "·"), (r"\div", "÷"),
                 (r"\left", ""), (r"\right", ""),
                 (r"\[", ""), (r"\]", ""), (r"\(", ""), (r"\)", "")):
        t = t.replace(a, b)
    t = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", t)      # \frac{a}{b} -> a/b
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)         # **bold** -> <strong>
    return t.replace("\n", "<br>").replace("[[", "[ [").replace("]]", "] ]")


for v, items in enumerate(versions):
    out = ["[[AdvancedFormat]]", "", f"[[Block:Survey {vid(v)}]]", "",
           "[[Question:DB]]", "[[ID:intro]]",
           f"<h3>{html.escape(FORM_TITLE, quote=False)}</h3>"
           f"<p>{html.escape(FORM_DESCRIPTION, quote=False)}</p>", "",
           "[[PageBreak]]", "",
           "[[Question:TE:SingleLine]]", "[[ID:rater]]",
           "Your name or email (so we can thank you — not shared):", "",
           "[[PageBreak]]", ""]
    for slot, it in enumerate(items):
        r1, r2 = display_models(it, slot)
        qid = it["item_id"].replace("-", "_")    # Qualtrics export tag (no hyphens)
        body = (f"<p><strong>Task:</strong> {_q(it['prompt'])}</p>"
                f"<p><strong>Response 1</strong><br>{_q(resp_plain(it['source'], r1))}</p>"
                f"<br>"                                        # empty line between responses
                f"<p><strong>Response 2</strong><br>{_q(resp_plain(it['source'], r2))}</p>"
                f"<p><strong>Which answer is better?</strong></p><hr>")  # underline below
        out += ["[[Question:MC:SingleAnswer]]", f"[[ID:{qid}]]", body,
                "[[Choices]]", "Response 1", "Response 2", "About the same", "",
                "[[PageBreak]]", ""]
    (HERE / f"qualtrics_{vid(v)}.txt").write_text("\n".join(out) + "\n", encoding="utf-8")

# ---- version_map.md ----------------------------------------------------------
by_type: dict[str, int] = {}
for it in pool:
    by_type[it["task_type"]] = by_type.get(it["task_type"], 0) + 1

md = ["# Item → version map & collection design", "",
      "> Auto-generated by `build_versions.py` (deterministic; re-run to regenerate).",
      "", "## Design (disjoint, multi-model — one survey per team)", "",
      f"- **{len(prompts)} prompts × {len(OPPONENTS)} opponents = {N} comparison "
      f"items.** Every comparison is **{DPO_TARGET} vs** one of "
      f"{', '.join(OPPONENTS)} (on-policy for the DPO run). Judge = {JUDGE} "
      "(cross-family).",
      f"- Task-type mix: " + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())) + ".",
      f"- **{NUM_VERSIONS} versions**, ~{QUESTIONS_PER_VERSION} questions each, "
      "**non-overlapping**; a prompt never repeats within a survey.",
      f"- **1 team per version** ({TEAM_SIZE} students) → every question gets "
      f"{TEAM_SIZE} labels.", "",
      "| version (team) | questions | rendered file |", "|---|---|---|"]
for v, items in enumerate(versions):
    md.append(f"| {vid(v)} | {len(items)} | [version_{vid(v)}.md](version_{vid(v)}.md) |")
md += ["", "## Coverage", "",
       f"- {N} comparison items over {NUM_VERSIONS} teams; {TEAM_SIZE} labels each.",
       "- Every comparison includes the DPO target → all are usable preference pairs.",
       "", "## Per-version item lists", ""]
for v, items in enumerate(versions):
    md.append(f"- **Version {vid(v)}** — {', '.join(it['item_id'] for it in items)}")
(HERE / "version_map.md").write_text("\n".join(md) + "\n", encoding="utf-8")

# ---- console report + invariants ---------------------------------------------
no_dup = all(len({it["source"] for it in vv}) == len(vv) for vv in versions)
all_target = all(it["target_model"] == DPO_TARGET for it in pool)
print(f"{len(prompts)} prompts x {len(OPPONENTS)} opponents = {N} items, "
      f"{NUM_VERSIONS} versions x ~{QUESTIONS_PER_VERSION}")
print("no prompt repeats within a version:", no_dup)
print("every comparison includes the DPO target:", all_target)
