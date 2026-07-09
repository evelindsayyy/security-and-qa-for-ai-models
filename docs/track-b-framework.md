# Track B — efficacy (evaluation pillar)

Track A (security pillar): [`track-a-framework.md`](track-a-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

Track B implements `tasks/` and `evaluator/`. Duke suites and benchmark references below.

Gateway catalog: [`gateway-models.md`](gateway-models.md). Structured outputs: [`data-model.md`](data-model.md) — Duke suites in `eval_runs` / `eval_results`, public benchmarks in `benchmark_runs`. GitLab: [`.gitlab/README.md`](../.gitlab/README.md).

---

## Layers

```text
1. Duke YAML suites (primary)
2. Adapted public benchmark subsets (optional)
3. Published external scores (report card reference only)
```

Record latency, tokens, cost, and failure rate on every run.

---

## Proposed Duke suites

| Suite | Audience | Focus |
|-------|----------|--------|
| IT support | Staff, students | Duke tech and access (`tasks/rubrics/it_support.yaml`) |
| Policy Q&A | All | Institutional policy |
| Document summarization | All | Neutral long-form summary |
| Student study | Undergrad | Concepts and steps — not graded submissions |
| Creative writing | Humanities | Draft feedback — not ghostwriting |
| Research literature | Faculty, grad | Paper summary and appraisal |
| Research workflow | Lab | Reproducibility, IRB norms — not legal advice |
| Med education | Med / biomedical grad | Teaching vignettes — not diagnosis or treatment |
| Coding snippet | CS, CoLab | Short code help — not full repos |
| Variation consistency | All | N rephrased prompts per intent |

---

## MVP suites 

First wave for gateway eval — not the full table above. Start on **one** cheap gateway model (e.g. GPT 4.1 Mini), then run the same suites on the **three-model pilot** with Track A.

| Priority | Suite | Notes |
|----------|-------|--------|
| P0 | IT support | Rubric exists: `tasks/rubrics/it_support.yaml` |
| P0 | Policy Q&A | Institutional policy |
| P1 | Document summarization | ROUGE-L + judge |
| P1 | Student study | Undergrad help — not graded submissions |

Other suites (creative writing, med education, coding, etc.) follow in later weeks. GitLab: [`.gitlab/README.md`](../.gitlab/README.md).

## Rollout

| Stage | Focus |
|-------|--------|
| Done | `evaluator/` + schemas; MVP suites; public-benchmark pilots; Postgres ingest; full `/api` (evals, benchmarks, POST jobs) |
| Next | Remaining Duke suites; charts in `frontend/` |
| Later | More benchmark subsets, variation overlay |

Step-by-step sequencing lives in the GitLab milestones.

---

## Public benchmarks

Standard academic benchmarks, separate from the judge-scored Duke suites: own runner in [`benchmarks/`](../benchmarks/), own frontend tab, and own `benchmark_runs` table ([`data-model.md`](data-model.md#efficacy--public-benchmarks-track-b)). Each benchmark brings its own scoring and per-item shape but shares one run envelope, so new benchmarks are a code change, not a schema migration.

**Implemented** (in `benchmarks/`):

| Benchmark | Headline metric | Probes |
|-----------|-----------------|--------|
| IFEval | pass-rate | Verifiable instruction-following constraints |
| TruthfulQA (MCQ) | accuracy | Factuality / misconception avoidance |
| MMLU (subset) | accuracy | Multitask knowledge across 57 subjects |
| ToMi | accuracy | Theory-of-mind belief tracking |
| Consistency | mean BERTScore F1 | Robustness to question rephrasing |

**Candidate** (not yet wired): DocBench / QASPER, MT-Bench, AlpacaEval, Berkeley Function Calling, SWE-bench Lite / HumanEval.

Catalog: [`tasks/benchmarks/manifest.yaml`](../tasks/benchmarks/manifest.yaml).

---

## Metrics

| Family | Metrics |
|--------|---------|
| MCQ / Q&A | Accuracy (TruthfulQA-style), LLM-as-judge + rubric |
| Summarization | ROUGE-L, LLM-as-judge |
| Creative writing | Judge (clarity, tone) |
| Coding snippet | Judge; execution check later |
| All | Latency, tokens, cost, failure rate |

---

## Out of scope (summer)

Full SWE-bench on gateway; clinical patient advice; multilingual sweeps; new Mistral runs (deprecated).

## Open

MVP+ priority (med vs research literature); benchmark license review; shared vs per-suite rubrics.
