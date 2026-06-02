# CLAUDE.md

Context for Claude Code working in this repository.

## What this project is

Duke Code+ summer project (10 weeks): a model evaluation and security framework for Duke's AI Gateway. The deliverable is a "nutrition label" dashboard that gives Duke deployment teams (security, AI Gateway, OIT) a defensible view of each model's quality, safety, operational cost, and security risk.

The project has three pillars, each owned by different teammates:

- **Security** — pre-inference scanning for malicious code in model files (separate teammate, separate code)
- **Safety** — adversarial red-teaming to probe for harmful outputs (separate teammate, separate code)
- **Efficacy** — quality of model responses on Duke-relevant tasks (this directory)

You are working on the **Efficacy** pillar. Do not touch the Security or Safety pillars unless explicitly asked.

## Where we are in the timeline

Week 3 of 10. We are in the "thin slice" phase: get one end-to-end run working on one model and one task suite, ugly but real. Coverage and polish come in weeks 4-6. Feature freeze is week 7. Validation is weeks 7-8. Final handoff is week 10.

The goal by end of this week is: one command in this directory evaluates one candidate model on the IT-support task suite (12 questions), produces a JSONL file of `EvaluationResult` rows, and prints a small aggregation table.

## The single most important rule

**Schema and version stability is non-negotiable.** Every result row written by the runner must conform to `schemas.py` and reference the locked rubric/suite/prompt versions. If a contract needs to change, bump the version string in a new file rather than editing in place. Mid-project edits to references break score comparability and the project's credibility.

Specifically:
- Do not edit `schemas.py` to change `EvaluationResult` field shape without bumping `SCHEMA_VERSION`.
- Do not edit `tasks/rubrics/it_support.yaml` in place. Copy to `it_support_v2.yaml` and bump `rubric_version`.
- Do not edit `tasks/it_support_v1.jsonl` in place. Same pattern.
- The judge and system prompts in `prompts/` are versioned files. New version, new file.

## Methodology — the lineage to respect

The design follows three published methodologies. When you make architectural decisions, these are the references:

- **HELM** (Liang et al., arXiv 2211.09110) — multi-metric reporting across three buckets (response quality, operational, robustness). Never collapse to a single "best model" score. The taxonomy is in `metrics.yaml`.
- **G-Eval** (Liu et al., arXiv 2303.16634) — structured judge prompts with task intro + criteria + evaluation steps + JSON output. The judge uses chain-of-thought via the evaluation_steps in the rubric YAML.
- **MT-Bench / Judging LLM-as-a-Judge** (Zheng et al., NeurIPS 2023) — judge biases (position, verbosity, self-preference). Judge model must come from a different family than candidates. Judge temperature is 0.

The full reading list is in `docs/Efficacy_Reading_List.docx`.

## Repository layout

```
evaluator/
├── CLAUDE.md                            # this file
├── schemas.py                           # EvaluationResult contract — DO NOT change shape without version bump
├── metrics.yaml                         # canonical metric taxonomy (3 HELM buckets)
├── candidate.py                         # Gateway client wrapper (to build)
├── judge.py                             # LLM-as-judge (to build)
├── runner.py                            # orchestration (to build)
├── aggregate.py                         # per-model summary (to build)
├── tasks/
│   ├── it_support_v1.jsonl              # locked task suite, 12 questions
│   └── rubrics/
│       └── it_support.yaml              # rubric: dimensions, weights, anchors, eval steps
├── prompts/
│   ├── system/
│   │   └── it_support_v1.txt            # system prompt for candidate (to build)
│   └── judge/
│       └── reference_based_v1.txt       # judge prompt template (to build)
└── results/
    └── <timestamp>_<suite>_<model>.jsonl  # output; one JSON object per line
```

## Conventions

**Python.** 3.11+. Dataclasses for typed records (already in schemas.py). Type hints encouraged. Use `pathlib.Path`, not string paths. No frameworks beyond stdlib + `openai`, `pyyaml`, `pytest` for now.

**Errors.** Never crash a run. If a candidate call fails, write a result row with `candidate_failed=True` and the error string, then continue. Same for `judge_failed`. Losing a single question is fine; losing an hour of compute to one bad response is not.

**Logging.** Print progress to stdout so a human watching the run knows it's alive. Save full request/response traces to `results/<run_id>_trace.jsonl` for debugging.

**Versioning.** Result row references versions of: schema, suite, rubric, system prompt, user prompt template, judge model, judge prompt. The `Adaptation` dataclass already enforces this.

**Reproducibility.** Candidate temperature: configurable per run, default 0.2. Judge temperature: always 0. Random seeds: log them in the run metadata if used.

**Caching.** Hash (model + system_prompt_version + user_prompt + temperature) to a cache key. Cache candidate responses to `cache/candidates/` and judge responses to `cache/judges/`. A re-run with the same inputs should not call the API again. This will save real Gateway budget.

## What NOT to build

These are out of scope for this week, even if Claude Code thinks they'd be nice:

- The dashboard UI (separate track, not in this directory)
- The security scanner (different teammate)
- The safety probes / red-teaming (different teammate)
- Multi-judge panels or pairwise comparison (post-freeze stretch)
- ML-BOM emission (post-freeze stretch)
- Human-rating UI for the validation study (week 7-8 work)
- Async / parallel execution (do this only if sequential is genuinely too slow)
- A web server / FastAPI endpoint
- A database — JSONL files are fine
- Anything involving Docker, Celery, Redis, Postgres

If you find yourself reaching for any of these, stop and check with the user.

## Honest limitations to remember

- The reference answers in `tasks/it_support_v1.jsonl` are PLACEHOLDER. The metadata header says so. Scores produced against them are sufficient to validate the pipeline runs, not to draw conclusions about model quality. Replace with OIT-staff-written references before reporting scores as meaningful.
- Judge bias is documented in the methodology but not corrected in v1. Validation study (weeks 7-8) will quantify it.
- IT support is single-turn. Multi-turn drift is out of scope.

## Useful files for context (read before architecting)

- `schemas.py` — the result-row contract
- `metrics.yaml` — taxonomy of what we measure across the three HELM buckets
- `tasks/rubrics/it_support.yaml` — the rubric the judge applies
- `tasks/it_support_v1.jsonl` — the locked task suite

If a question would change the schema or rubric, ask the user before changing. Otherwise proceed.
