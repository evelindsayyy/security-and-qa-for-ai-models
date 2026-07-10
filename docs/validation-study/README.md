# Judge Validation Study — design

> **Status:** the design and survey-generation machinery are complete. The
> comparison **pairs are illustrative** (hand-written strong-vs-weaker answers
> that show the survey format); the real pairs are generated in Week 8 from two
> models on the frozen open-ended suites, and the references behind them are still
> placeholder (not OIT-validated). Not yet wired into the runner.

## Goal

Measure how well the automated **LLM-as-judge** agrees with **humans** on the
open-ended tasks (email drafting, plain-language rewriting, tutoring, …), so the
open-ended rankings on the AI Model Advisor dashboard are trustworthy — not just
the verifiable SQL/JSON/numeric tasks that have an execution oracle.

**Deliverable:** `docs/validation-study.md` — Cohen's κ (judge vs humans),
human–human agreement (the ceiling), documented judge biases, and a
Bradley-Terry rating per model.

## The pipeline (five steps)

This follows the standard LLM-judge-calibration pipeline (MT-Bench / Chatbot
Arena lineage). Steps 1–3 are the calibration core; step 4 turns pairwise votes
into an absolute rating and is the bridge to reward modeling.

### 1. Collect preferences
- Sample prompts from the frozen open-ended suites (email, plain-language,
  tutoring, summarization).
- Per prompt, generate **two responses A/B** — from **two different models**
  (clearer signal, recommended for the first study) or one model at two
  temperatures (subtler). Reuse `candidate.py` + `runner.py`.
- Humans pick the winner, or **"tie."**
- Store **triples `(prompt, chosen, rejected)`** — this is both the calibration
  data and, later, the DPO / reward-model dataset (the Track-3 bridge).
- **Tie handling:** keep ties for the agreement stats (forcing a choice adds
  noise); **drop ties** when forming `(chosen, rejected)` pairs (a tie is not a
  preference).

### 2. Measure rater agreement — FIRST, as a gate
- ≥3 raters per item (odd → clean majority). Compute **human–human agreement**:
  - **Fleiss' κ** for the rater pool (the block design routes different raters to
    different items).
  - Cohen's κ only where exactly two fixed raters share the same items.
- **Low κ means the task is ambiguous — fix the instructions/rubric before
  trusting ANY data.** Validate your ruler before you measure with it. This gates
  everything downstream: don't calibrate the judge against humans who don't agree
  with each other.

### 3. Calibrate the judge
- Run the LLM-judge in **pairwise mode** on the same pairs (extend `judge.py` +
  a `reference_free_pairwise` prompt; reuse `compare_judges.py`).
- Headline: **κ(judge vs human-majority-consensus)** across all items (+ raw %
  agreement).
- **Probe biases deliberately** (controlled manipulations, not just observational
  correlations):
  - **Position bias** — swap A/B order; measure how often the pick flips.
  - **Length bias** — pad one response with filler that adds no content; see if
    the judge prefers the longer one.
  - **Self-preference** — if a candidate shares the judge's model family, check
    whether the judge over-selects it.

### 4. Turn pairwise into a ranking
- Pairwise is O(n²) and gives no absolute score, so aggregate to a rating with
  **Bradley-Terry** (preferred over Elo here: Elo is online/order-dependent, built
  for a streaming feed; a fixed collected dataset wants BT's clean maximum-
  likelihood fit).
- With **3 candidate models** (Qwen2.5-7B-Instruct, GPT 4.1 Mini,
  GPT 4.1 Nano) the ratings are a genuine 3-way **leaderboard**, and the fit
  doubles as the **reward-model foundation** for the alignment track.
- **Scope line (Track-3 guardrail):** fitting BT to produce a *ranking / rating*
  is **in-scope evaluation** (this is what Chatbot Arena does). Using BT — or DPO —
  to *train / improve a model* is **Track 3**: it stays local on a branch and is
  **never pushed until the mentor signs off.** Same math, different purpose,
  different rules.

### 5. Tools
- Python + the existing harness (`candidate.py` / `judge.py` / `runner.py`).
- Annotation: **Google Forms / Qualtrics** (the "spreadsheet+" option) → CSV export.
- Stats (W8 setup — none installed yet): `scikit-learn` (`cohen_kappa_score`),
  `statsmodels` (`fleiss_kappa`), Bradley-Terry via `choix` or a short MLE /
  logistic fit.

## Collection scheme (disjoint blocks — one survey per team)

One survey per **Code+ team** (~3–5 students), split into **non-overlapping**
blocks so every question is in exactly one survey and the whole team rates it
(3–5 labels each). To reach ~100 questions from 54 prompts, each prompt is turned
into **model-vs-model comparisons**: every comparison is **Qwen2.5-7B-Instruct vs**
one opponent (GPT 4.1 Mini or GPT 4.1 Nano). Generated deterministically by
[build_versions.py](build_versions.py); the realized design:

| Knob | Value | Note |
|---|---|---|
| Prompts × opponents | **54 × 2 = 108 comparisons** | every comparison includes Qwen (the DPO target) → all are usable preference pairs |
| Candidate models | **3** | Qwen2.5-7B-Instruct (DPO target), GPT 4.1 Mini, GPT 4.1 Nano; judge = Llama 4 Maverick (cross-family) |
| Versions (teams) | **12** | ~9 questions each, **non-overlapping**; a prompt never repeats within a survey |
| Raters per version | **3–5** | one team per survey → every question gets 3–5 labels |

Two things this buys: (1) a real 3-model **Bradley-Terry ranking**, and (2) an
**on-policy preference dataset for the Qwen DPO run** (see the analysis plan's
"survey → DPO data"). Note: a *prompt* appears in ~2 teams' surveys (different
opponent each time) — no student sees a repeat. Full item→version assignment:
[version_map.md](version_map.md).

## What you must encode (so results map back)

For every response a rater sees, you (the researcher) must recover:
**item_id** (which comparison), **version_id** (which survey), **rater_id** (who),
and **response order** (which underlying answer was "Response 1" vs "Response 2").
In Forms/Qualtrics each version is a fixed form, so item_id + order are known from
the form; rater_id from a required field; the pick is the answer. Export to CSV,
join on these keys. Order is counterbalanced within each survey (alternating by
item) so position bias is measurable.

## Artifacts in this folder
- This design note — the five-step pipeline + the collection scheme.
- The [analysis plan](analysis_plan.md) — the exact κ / Fleiss / Bradley-Terry
  computations + library calls.
- The generated survey set: [version_map.md](version_map.md) + 12 rendered surveys
  (`version_01.md` … `version_12.md`) and 12 **Qualtrics** import files
  (`qualtrics_01.txt` … `qualtrics_12.txt`, see [QUALTRICS_IMPORT.md](QUALTRICS_IMPORT.md)),
  built from [item_pool.jsonl](item_pool.jsonl) + [responses.jsonl](responses.jsonl) by
  [build_versions.py](build_versions.py).

**Decided:** disjoint per-team surveys; **Qualtrics** (Advanced Format import);
multi-model — Qwen2.5-7B-Instruct (DPO target, served on the DCC) vs GPT 4.1 Mini /
GPT 4.1 Nano → 108 comparisons / 12 teams. Responses generated (162); surveys
filled and ready to import.
