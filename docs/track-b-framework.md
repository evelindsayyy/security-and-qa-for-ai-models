# Track B — efficacy (evaluation pillar)

Track A (security pillar): [`track-a-framework.md`](track-a-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

Track B implements `tasks/` and `evaluator/`. Duke suites and benchmark references below.

Gateway catalog: [`gateway-models.md`](gateway-models.md). Structured outputs: [`data-model.md`](data-model.md) (`eval_runs`, `eval_results`). GitLab: [`.gitlab/README.md`](../.gitlab/README.md).

---

## Spike vs production

| Phase | Location |
|-------|----------|
| W2–W3 spikes | `testing/eval/`, `testing/gateway/` |
| W3+ production | `evaluator/` |

---

## Layers

```text
1. Duke YAML suites (primary)
2. Adapted public benchmark subsets (optional)
3. Published external scores (nutrition label reference only)
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

First wave for gateway eval — not the full table above. **Week 3:** run on **one** cheap gateway model (e.g. GPT 4.1 Mini). **Week 4+:** same suites or more on the **three-model pilot** with Track A.

| Priority | Suite | Notes |
|----------|-------|--------|
| P0 | IT support | Rubric exists: `tasks/rubrics/it_support.yaml` |
| P0 | Policy Q&A | Institutional policy |
| P1 | Document summarization | ROUGE-L + judge |
| P1 | Student study | Undergrad help — not graded submissions |

Other suites (creative writing, med education, coding, etc.) follow in later weeks. GitLab: [`.gitlab/README.md`](../.gitlab/README.md).

## Rollout

| When | Focus |
|------|--------|
| **W3** | `evaluator/` + schemas; **MVP suites** on **one** gateway model |
| **W4** | MVP (+ more) suites on **three** pilot models (with Track A) |
| **W5–6** | Remaining Duke suites; charts in `frontend/` |
| Later | Benchmark subsets, variation overlay |

---

## Public benchmarks (reference)

| Benchmark | Use |
|-----------|-----|
| TruthfulQA MCQ | W2 spike — optional column on label |
| IFEval, DocBench / QASPER | Optional subsets |
| MT-Bench, AlpacaEval | Quality reference on label |
| Berkeley Function Calling | Agentic / tool-use |
| SWE-bench (full) | Not on gateway API |
| SWE-bench Lite / HumanEval | Optional coding column |

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
