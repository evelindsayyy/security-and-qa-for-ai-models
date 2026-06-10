# Week 4 demo day — runbook, slide content, triage notes

> Pre-demo audit run Wednesday morning (2026-06-10). Dashboard crawl: 27 URLs,
> all 200, no broken links, no `<script>` tags (no console-error risk), no
> empty-response artifacts on any visible run.

## Demo click path (rehearsal order)

1. `/` — hub with pillar counts
2. `/scans` → `/scans/neimasilk--modelscan-extension-mismatch-poc` (the critical/95 PoC) → `/scans/gpt2` (low/18 contrast)
3. `/eval-run` — point out the **judge column** and the new **dynamic dimension columns** (policy_qa dims appear alongside IT-support dims)
4. `/eval-run/20260609T171541Z_policy_qa_v1_gpt-5-chat` — the policy_qa run: citation_precision 2.5 stands out against the 5.0s
5. `/benchmarks` → one IFEval detail page (Jack's pillar reflected)
6. `/models` — gateway catalog
7. `docs/rubric-design.md` open in editor for the methodology question

Backup plan: keep a second tab pre-loaded on `/eval-run` before the meeting;
all pages read from disk (no live Gateway calls), so the only live-demo risk
is the laptop, not the Gateway.

**Stale-data decision needed before rehearsal:** Tuesday's three cross-judge
runs (timestamps `20260609T1717*`/`1718*`/`1720*`) are superseded by
Wednesday's clean trio (`20260610T1716*`–`1723*`, identical candidate
responses, gpt-oss at full coverage). Both sets currently show on `/eval-run`,
so gpt-5-chat appears six times. Either delete the Tuesday three before the
demo, or be ready to explain the duplication. Suggested cleanup:

```bash
rm evaluator/results/20260609T1717*_it_support_v1_gpt-5-chat*.jsonl \
   evaluator/results/20260609T1718*_it_support_v1_gpt-5-chat*.jsonl \
   evaluator/results/20260609T172014Z_it_support_v1_gpt-5-chat*.jsonl
```

---

## Slide 1 — A second task suite: Duke policy Q&A

**The rubric discriminates — scores are not all 5s.**

| Dimension (policy_qa_v1 rubric) | gpt-5-chat mean (4 Qs) |
|---|---|
| accuracy | 5.0 |
| **citation_precision** | **2.5** |
| policy_adherence | 5.0 |
| contextualization | 5.0 |
| tone | 3.0 (of 3) |
| **Overall (weighted)** | **4.25 / 5** |

- New task suite: 4 hand-written Duke policy questions (FERPA, data
  classification, Box vs Google Drive, AI-tool use). References are
  PLACEHOLDER pending policy-office validation (week 5).
- The judge reads grading criteria from the rubric file — adding this task
  required **zero judge-code changes** (shared dimension library + rubric-aware
  prompt template).
- The story: a strong model answers *correctly* but doesn't *cite Duke policy
  sources precisely* — exactly the kind of gap a deployment team needs to see.

## Slide 2 — Does the judge choice change the verdict?

**Three judges, same 12 IT-support answers from gpt-5-chat (byte-identical).**

| Judge | Overall | Completeness (the discriminator) | Coverage |
|---|---|---|---|
| Llama 3.3 | 5.00 | 5.00 | 12/12 |
| Llama 4 Maverick | 4.90 | 4.83 | 12/12 |
| gpt-oss-120b | 4.63 | 4.00 | 12/12 |

- Spread of **0.37 overall** between most lenient and strictest judge on
  identical answers; 8 of 12 questions show ≥0.5 disagreement.
- gpt-oss-120b's deductions cite specific reference omissions (backup MFA
  method, print-fund balance check) — strict but *defensible*.
- Llama 3.3 gave perfect 5s on everything — a leniency ceiling, which
  questions its value as a judge.
- Why this matters: it quantifies judge sensitivity ahead of the weeks 7–8
  human-rater validation study, which decides which judge tracks humans.
- (Methodology footnote: gpt-oss initially failed 9/12 by exhausting its
  token budget on hidden reasoning — fixed with a configurable judge budget;
  the same artifact affects reasoning *candidates* and is now auto-detected.)

---

## Afternoon triage (fill in during/after the meeting)

### Raw notes


### Triage

| Feedback item | Bucket (must-do this week / week 5 / deferred) | Notes |
|---|---|---|
|  |  |  |

### Thursday decision

Per TASK.md the default is the **live frontend button** unless feedback says:
- "more rubrics / more depth" → third task rubric + more candidate models
- "fit into deployment workflow" → `/models/<id>` nutrition-label view

**Decision:** Live frontend button — "Start run" form → allowlist-validated
subprocess → progress bar → detail page.

**Why:** TASK.md's default for non-directional feedback, and the most
demoable artifact for next Wednesday: the demo no longer requires a terminal.
