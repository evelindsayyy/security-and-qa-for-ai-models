# Evaluation (Track B)

Track A: [`security-framework.md`](security-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

Track B implements `tasks/` and `evaluator/`. This doc lists proposed suites and benchmark references.

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

**Not in Track B:** harm, jailbreaks, academic dishonesty (Track A safety).

---

## Rollout

| When | Suites |
|------|--------|
| Weeks 3–4 | IT support, summarization, student study, policy Q&A |
| Weeks 4–6 | Creative writing, research literature, med education, coding |
| Later | Research workflow, variation overlay, benchmark subsets |

---

## Public benchmarks (reference)

| Benchmark | Use |
|-----------|-----|
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
| Summarization | ROUGE-L, LLM-as-judge |
| Q&A, study, policy, med, research | LLM-as-judge + rubric |
| Creative writing | Judge (clarity, tone) |
| Coding snippet | Judge; execution check later |
| All | Latency, tokens, cost, failure rate |

---

## Out of scope (summer)

Full SWE-bench on gateway; clinical patient advice; multilingual sweeps.

## Open

MVP+ priority (med vs research literature); benchmark license review; shared vs per-suite rubrics.
