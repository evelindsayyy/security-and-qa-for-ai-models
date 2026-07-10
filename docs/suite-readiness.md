# Task-suite launch readiness

_Last audited: 2026-07-09 · guard: `unit_tests/test_suite_readiness.py`_

This document records the launch-readiness of every task suite a user can pick
on the **Start an evaluation run** form (`/eval-run/new`). "Ready" is not a
subjective judgment — it's the set of properties enforced by
`test_suite_readiness.py`, re-checked in CI on every change.

## Summary — all 9 surfaced suites are launch-ready

| Suite | Scoring | Q | Rubric dimensions / check | Status |
|---|---|---:|---|---|
| `it_support_v1` | LLM-judge | 12 | accuracy · completeness · policy_adherence · tone | ✅ ready |
| `policy_qa_v1.1` | LLM-judge | 12 | accuracy · citation_precision · policy_adherence · contextualization · tone | ✅ ready |
| `summarization_v1` | LLM-judge | 6 | faithfulness · coverage · concision · tone | ✅ ready |
| `sql_duke_v2` | execution | 14 | SQL — run query, compare rows | ✅ ready |
| `json_duke_v1` | execution | 6 | JSON — parse + compare | ✅ ready |
| `numeric_duke_v1` | execution | 6 | numeric — extract + tolerance-compare | ✅ ready |
| `email_drafting_v1` | LLM-judge | 5 | completeness · clarity · tone · structure | ✅ ready |
| `tutoring_v1` | LLM-judge | 5 | correctness · pedagogy · completeness · tone | ✅ ready |
| `plain_language_v1` | LLM-judge | 5 | faithfulness · simplicity · completeness · tone | ✅ ready |

**71 questions across 9 suites** — 3 execution-scored (26 Q) and 6 judge-scored (45 Q).

## What "launch-ready" means (the checks)

Each property below is a test in `test_suite_readiness.py`; a regression fails CI.

1. **Structural.** Metadata line parses; every row has a unique `id` and a
   non-empty `question`; the file's row count equals `suite_question_count()`
   (the number the form's cost estimate uses).
2. **Badge honesty.** The form's scoring badge (**RUN & CHECK** vs **LLM-JUDGED**)
   equals the file's own `scoring` metadata. This matters because the *runner*
   routes on the file — `scoring: execution` auto-skips the LLM judge — so a
   mismatched badge would misrepresent how the suite is actually scored.
3. **Execution golds reachable.** For SQL/JSON/numeric suites, every row has an
   `expected` gold; JSON/numeric golds pass when fed back through their own
   checker; SQL `setup` scripts build a clean throwaway database. For
   `sql_duke_v2`, a **correct reference query is run for all 14 questions and
   must pass its gold** — this catches the one failure a structural check can't:
   a gold no correct query can produce, which would silently tank a pass-rate.
4. **Judge suites gradeable.** Every row carries a non-empty `reference` (the
   judge grades against it), and the paired rubric resolves to a non-empty set
   of dimensions.

## The one honest limitation — judge references are PLACEHOLDER

The judge suites (`email_drafting`, `tutoring`, `plain_language`, and the earlier
`it_support` / `policy_qa` / `summarization`) carry **hand-written reference
answers that have not been validated by a Duke office** (communications,
instruction, or policy). Each file's metadata says so explicitly. This is the
same documented limitation the project has carried since week 4: these scores are
**pipeline validation, not authoritative benchmarks**.

This does not block launching — the pipeline runs end-to-end and produces
comparable scores. It bounds the *interpretation*: "how does model A compare to
model B on our rubric" is sound; "this is Duke's official quality bar" is not.

## Why the suites weren't just edited to "fix" this

Every suite here is **frozen** — SHA-pinned in `evaluator/frozen_contract.yaml`
since the W7 freeze and enforced by `test_contract_freeze.py`. Editing a suite in
place changes its hash (fails CI) and, more importantly, breaks score
comparability across runs — the project's single most important rule.

**Upgrade path** (if stronger references or more/harder questions are wanted
later): add a **new versioned file** (e.g. `sql_duke_v3`, `tutoring_v2`), wire it
into `eval_launch.SUITES`, and append it to the freeze manifest in a follow-up
freeze. The existing entries stay pinned. This is the sanctioned way to evolve a
frozen contract.

## Two guards, two jobs

| Guard | Answers |
|---|---|
| `test_contract_freeze.py` | "Is the suite **unchanged** since the freeze?" (comparability) |
| `test_suite_readiness.py` | "Is the suite **correct and launchable**?" (a frozen file can still be broken) |

## Built but not yet on the form

These suites exist and are frozen, but are intentionally *not* surfaced on the
launch form yet. They're the difficulty-spread / robustness extensions — surface
them the same way (add to `SUITES`) when the demo calls for them:

- `sql_duke_hard_v1` (4 Q) — SQL traps built to surface judge-vs-execution divergence
- `email_drafting_hard_v1`, `plain_language_hard_v1`, `tutoring_hard_v1` (3 Q each) — harder judge variants
- `robustness_v1` (20 rows) — perturbation suite for the robustness report
- `sql_duke_v1` (5 Q) — the SQL pilot, superseded by `sql_duke_v2`
