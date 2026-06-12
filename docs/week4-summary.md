# Week 4 summary — Efficacy pillar (slide-ready)

> Audience: stakeholder update, 1–2 slides. Numbers reproducible with
> `cd evaluator && python compare_judges.py --from-results --suite <suite>`.
> All scores rest on PLACEHOLDER references until the week-5 OIT/policy
> review — pipeline + methodology validation, not authoritative quality claims.

## Slide 1 — What shipped this week

- **Live frontend**: evaluations launch from a browser form (allowlist-validated,
  cost preview, live progress bar) — no terminal needed for demos
- **Second task suite**: Duke policy Q&A, 12 questions (FERPA, data
  classification, AI use, payments, research data), versioned v1 → v1.1
- **Rubric system generalized**: judge reads grading criteria from the rubric
  file (shared dimension library + rubric-aware prompt) — new tasks need zero
  judge-code changes
- **Judge selected with data**: cross-judge experiments → interim decision
  recorded in `docs/judge-selection.md`
- **Pipeline hardened**: reasoning-model empty responses detected and failed
  honestly (was: silent fake scores); crash-safe caches; 106 unit tests
- **Week-5 groundwork**: draft Postgres schema + idempotent JSONL→DB loader
  (dry-run by default); DCC notes + smoke job

## Slide 2 — What we learned (the three findings)

**1. The policy rubric discriminates — no ceiling effect.**

| Candidate (policy_qa_v1.1, Maverick judge) | Overall | citation_precision |
|---|---|---|
| gpt-5-chat | 4.33 | 2.83 |
| GPT 4.1 Mini | 3.74 | 2.00 |
| Llama 4 Scout | 3.31 | 1.67 |

Every model struggles to cite specific Duke policy sources — exactly the
compliance-relevant gap the rubric was designed to surface.

**2. Judge choice changes numbers, not conclusions.**
Three judges, identical answers: 100% rank concordance. Maverick separates
strong from weak best (0.99 gap vs 0.77 / 0.45) and showed no favoritism
toward its own model family (scored its family-mate lowest). → **Llama 4
Maverick primary judge; gpt-oss-120b strict spot-check; Llama 3.3 dropped
(all-5s leniency ceiling).** Final arbiter: weeks 7–8 human validation study.

**3. Reasoning models need explicit token budgets.**
gpt-5-mini/nano spend their completion budget on hidden thinking and return
empty text at default settings (nano needs ~4000 tokens, 10× gpt-5-chat for
the same questions — a real operational-cost finding for the nutrition label).
The pipeline now detects this and fails honestly instead of judging blanks.

## Current matrix (Maverick judge, v2 prompt, latest run per cell)

| | it_support_v1 | policy_qa_v1.1 |
|---|---|---|
| gpt-5-chat | 4.90 | 4.33 |
| gpt-5-mini | 5.00 | — |
| gpt-5-nano | 4.93 | — |
| GPT 4.1 Mini | 4.24 | 3.74 |
| Llama 4 Scout | 3.91 | 3.31 |

Stability check: GPT 4.1 Mini re-run this week scored 4.24 vs 4.26 in week 3
(different sampled answers, different judge-prompt version) — the pipeline
measures consistently.

## Locked for week 5

- OIT meeting asks: ticket categories **by volume** + anonymized real
  phrasings (content validity), expert-written references, and experts
  **grading 3–5 real outputs with the rubric** before approving anchors
  (criteria-drift protocol) — see `docs/rubric-design.md` § validity
- Team review of `evaluator/db/efficacy_schema.sql`, then `--apply` the
  loader and point the dashboard at Postgres
- Third task suite (document summarization — first reference-metric + judge
  hybrid per track-b-framework P1)

## Open questions

- Validation study design details (rater count, sample size vs the ≥30 in
  the rubric spec, Kappa thresholds) — weeks 7–8
- `models` table ownership (cross-pillar join key) — team decision
- Whether policy_qa scores change materially once references are
  policy-office-written (expected: yes, that's the point of week 5)
