# Rubric Design Methodology

How the Efficacy pillar designs evaluation rubrics. Authoritative reference for adding a new rubric, revising an existing one, or explaining the design choices to mentors and stakeholders.

## TL;DR

- **HELM** (Liang et al. arXiv 2211.09110) says: metrics are task-conditional. No universal rubric. Pull a shared dimension library; pick the relevant subset per task.
- **G-Eval** (Liu et al. arXiv 2303.16634) says: every dimension has four parts — definition, scale, anchored anchors, and chain-of-thought evaluation steps. Not "rate this 1-5."
- **MT-Bench** (Zheng et al. NeurIPS 2023) says: name the judge biases in the rubric's limitations, then correct for them in a validation study against human raters.
- **Versioning** says: once a task suite has been run against a rubric, that rubric is immutable. Revisions go in `<task>_v2.yaml`; the runner records `rubric_version` per row.

If you're about to design a new rubric, jump to [The 8-step design process](#the-8-step-design-process).

---

## The architecture

```
evaluator/tasks/rubrics/
├── _shared_dimensions.yaml   # the dimension library (definitions, scales, anchors)
├── it_support_v1.yaml        # locked v1 (currently what the runner reads)
├── it_support_v1.1.yaml      # DRAFT — same semantics as v1, refactored to reference shared
├── policy_qa_v1.yaml         # DRAFT — new task, anchors not yet expert-calibrated
└── <new_task>_v1.yaml        # new task rubrics land here
```

### Shared dimension library

`_shared_dimensions.yaml` holds the dimensions that recur across tasks — `accuracy`, `completeness`, `policy_adherence`, `tone`, plus task-specific ones we know we'll reuse (`faithfulness`, `coverage`, `concision` for summarization; `citation_precision`, `contextualization` for QA).

Each dimension has:
- `definition` — what it measures
- `scale` — `[min, max]` integer range (typically `[1, 5]` for factual dimensions, `[1, 3]` for subjective ones)
- `anchors` — concrete descriptions at 1, 3 (or 2 for `[1,3]` scales), and 5. The judge picks the anchor that best matches; the rubric forces specificity.

Definitions/scales/anchors are **immutable once a task rubric depends on them**. To revise a dimension, add a v2 entry (e.g., `accuracy_v2`) and migrate task rubrics explicitly. This preserves cross-run score comparability.

### Task-specific rubrics

A task rubric (`<task>_<version>.yaml`):
- Names which shared dimensions apply, with **task-specific weights**
- Adds **task-specific dimensions** inline if needed
- Provides a **task-specific `task_note`** per dimension — concrete guidance for the judge ("for IT support, Duke-specific facts means NetID URLs, Duo flow, …")
- Provides **task-specific `evaluation_steps`** — chain-of-thought walking the judge through how to apply each dimension to this task
- Names the **task's known limitations** — what this rubric is NOT measuring

### Empty-response branch

Every rubric's `evaluation_steps` starts with:

> If the candidate response is empty, whitespace-only, or a bare refusal that does not engage the question, score 1 on every dimension and write 'empty response' or 'refusal without engagement' as the rationale. Do not confabulate. Skip the rest of these steps.

Reason: in week-3 runs, reasoning models (gpt-5-mini, gpt-5-nano) sometimes spent their full `max_tokens` budget on hidden tokens and emitted no visible text. Without this branch, the judge confabulated 5/5 ratings for empty inputs — that's not "the model is great", that's "the judge made something up".

---

## The 8-step design process

For each new task you want to add. Don't skip steps; pilot data without expert calibration is worse than no data.

### Step 1 — Identify the task's distinguishing failure modes

Don't start from "what dimensions exist." Start from "what does a bad response on this task *look like*?"

Write 3-5 example failure modes. Those become candidate dimensions.

**Example — policy QA:**
- "Wrong policy section cited" → suggests `citation_precision` as a task-specific dimension
- "Ignores user's stated role / department" → suggests `contextualization`
- "Quotes an outdated policy version" → suggests an `accuracy` facet for recency

### Step 2 — Collect 5-10 expert reference responses

Same standard as the locked suite JSONL itself. Get real domain experts (Duke OIT for IT support, Duke policy office for policy QA, etc.) to write what a great response looks like.

You can't design anchors without seeing the high end. If you skip this step, your "5" anchor describes your *intuition* about a great response, not a real one.

### Step 3 — Calibrate anchors against the expert references

For each dimension, write what a 1, 3, and 5 (or 1, 2, 3 for coarse scales) look like relative to the references you collected.

- **5** = "as good as the expert reference"
- **3** = "covers main point but misses a meaningful detail"
- **1** = "wrong, harmful, or fundamentally incomplete"

Use concrete examples in the anchor text. "Includes the URL but not the Duo step" is better than "missing a step."

### Step 4 — Set weights

Heuristic ordering: weight by how much a 1 vs. 5 on this dimension would affect a *real Duke user's outcome*.

- `accuracy` is almost always heavily weighted.
- For summarization, `faithfulness` rivals accuracy.
- For policy QA, `citation_precision` rivals accuracy.
- `tone` is almost always lightest (it's a 1-3 scale and a soft metric).

Weights must sum to 1.0. Record the rationale in the rubric's `aggregation.note` field — future maintainers will ask "why is X weighted 0.30?"

### Step 5 — Write `evaluation_steps` as chain-of-thought

Walk the judge through how to apply each dimension. Start with the empty-response branch. End with "output valid JSON, no prose, no fences."

Each step should reference the rubric's `task_note` fields where they apply. The judge sees the task notes via the rubric YAML inlined into the prompt template.

The IT support `evaluation_steps` is a good shape — 10-11 numbered instructions, each one applies to a specific dimension or to the output format.

### Step 6 — Pilot test

Run the rubric on 2-3 questions with one candidate model. Read the judge's rationales carefully.

Diagnostic questions:
- Did the judge cite a specific anchor description, or invent its own scoring?
- Are the scores discriminating, or all 5s / all 3s?
- Are the rationales specific ("missed the Duo step in question 4") or generic ("response was good")?

If the rubric is unclear, the judge will be vague. Fix the anchors. Re-pilot.

### Step 7 — Human-validate the pilot

Get one Duke domain expert (mentor, OIT contact, policy office staff) to score the same 2-3 responses against the same rubric.

Compare anchor-by-anchor:
- **Same anchor picked, same score** → rubric is working
- **Different anchor picked, same score** → coincidence; needs more samples
- **Different score** → anchors are ambiguous; revise

This is a small-scale precursor to the validation study in weeks 7-8. It catches ambiguity *before* you waste budget running the full pipeline.

### Step 8 — Lock and version

Save as `<task>_v1.yaml`. Update the runner's `--rubric` flag default (or pass per run). Document the new task in `evaluator/README.md`.

After this, the rubric is **immutable**. Revisions go to `<task>_v2.yaml`. The runner's `Adaptation.rubric_version` field records which one was used.

---

## Versioning

Match the locked-file pattern from `CLAUDE.md`:

- New files for new versions: `it_support_v1.yaml` → `it_support_v1.1.yaml` → `it_support_v2.yaml`.
- **Minor bumps** (e.g., `v1` → `v1.1`) are for structural changes that don't affect semantics — refactoring inline dimensions to reference the shared library, fixing typos in the description, etc. Same scores expected.
- **Major bumps** (e.g., `v1.x` → `v2`) are for semantic changes — new anchor wording, new dimensions, revised weights, new evaluation_steps. Different scores expected.
- The `rubric_version` string lands in every `EvaluationResult` row's `Adaptation` block, so result history stays interpretable.

Cross-run comparability requires the rubric to not move under you. If you find yourself wanting to "just tweak" a locked rubric, that's the signal to write a v2.

---

## Common pitfalls

### Pitfall 1 — Designing dimensions before seeing failure modes

If you start from a list of dimensions ("accuracy, completeness, helpfulness, …") and try to fit them to a task, you'll miss the dimensions specific to that task. Start from failures. Dimensions emerge.

### Pitfall 2 — Vague anchors

"Mostly correct" tells the judge nothing. "Missing the MFA step" tells the judge exactly where to score 3 instead of 5. The anchor text is the rubric.

### Pitfall 3 — Ignoring the empty-response case

See the week-3 gpt-5-mini incident. Always include the empty/refusal branch as step 1 of `evaluation_steps`.

### Pitfall 4 — Over-weighting tone

Tone is subjective and runs on a 1-3 scale, which makes it noisy. Weight it ≤ 0.15 across all task rubrics unless you have a specific reason. If stakeholders push for "but tone matters!" — show them the validation-study Cohen's Kappa numbers from week 7-8 and let the data make the case.

### Pitfall 5 — Picking weights before pilot data

Set weights from domain reasoning (Step 4). After pilot validation (Steps 6-7), revisit them. Don't assume your intuition about which dimension matters most survives contact with real responses.

### Pitfall 6 — Skipping the expert reference collection

If your "5" anchor is what *you* think great looks like rather than what a *Duke OIT staff member* thinks great looks like, your scores measure a model's similarity to your intuition, not its similarity to expert performance.

### Pitfall 7 — Inheriting a task rubric for a different task

Copy-pasting `it_support.yaml` and renaming dimensions is faster than designing from scratch, but every dimension you inherit is a dimension you didn't think about. Walk through Step 1 fresh.

---

## How this fits the project plan

- **Week 4:** Refactor `it_support_v1` → `it_support_v1.1` referencing shared library (mechanical, ~30 min). Design `_shared_dimensions.yaml` (this exists as a draft already). Identify which 3-5 Duke tasks the project will cover — talk to mentor.
- **Week 5:** Apply OIT-reviewed references → `it_support_v2.jsonl` + `it_support_v2.yaml`. Design + pilot one new rubric (likely `policy_qa_v1`). Re-weight after pilot.
- **Week 6:** Design + pilot a second new rubric. Run pipeline against all locked rubrics.
- **Week 7:** Feature freeze. All rubrics locked.
- **Weeks 7-8:** Validation study runs against multiple rubrics, not just IT support.

The shared library means a single edit (e.g., revising the `accuracy` definition) propagates to every task rubric that references it. Without the library, every task rubric has its own copy and they drift.

---

## Related files

- `evaluator/tasks/rubrics/_shared_dimensions.yaml` — the dimension library
- `evaluator/tasks/rubrics/it_support_v1.yaml` — locked v1 (what the runner currently reads)
- `evaluator/tasks/rubrics/it_support_v1.1.yaml` — DRAFT refactor referencing shared
- `evaluator/tasks/rubrics/policy_qa_v1.yaml` — DRAFT new task rubric
- `evaluator/metrics.yaml` — taxonomy of what the Efficacy pillar measures (three HELM buckets)
- `evaluator/README.md` — known limitations section names the rubric issues this doc addresses

## Citations

1. Liang, Percy, et al. *Holistic Evaluation of Language Models.* arXiv 2211.09110, 2022.
2. Liu, Yang, et al. *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment.* arXiv 2303.16634, 2023.
3. Zheng, Lianmin, et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023.
