# Track B — efficacy (evaluation pillar)

Track A (security pillar): [`track-a-framework.md`](track-a-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

Track B implements `tasks/` and `evaluator/`. Duke suites and benchmark references below.

Gateway catalog: [`gateway-models.md`](gateway-models.md). Structured outputs: [`data-model.md`](data-model.md). GitLab: [`.gitlab/README.md`](../.gitlab/README.md).

**Red team** (jailbreaks, academic dishonesty, harm) is Track A **safety** — not efficacy.

---

## Spike vs production

| Phase | Location |
|-------|----------|
| W2–W3 spikes | `testing/eval/`, `testing/gateway/` |
| W3+ production | `evaluator/` |

---

## Week 2 completed (gateway)

| Work | Location | Notes |
|------|----------|-------|
| TruthfulQA MCQ pilot | `testing/eval/truthfulqa/` | n=50; gpt-5.4 **0.90**, Mistral on-site **0.74**, Llama 3.3 **0.62** |
| LiteLLM compare / smoke | `testing/gateway/` | Latency, tokens; env-based API key |
| OpenAI SDK smoke | `testing/test_gateway.py` | `GPT 4.1 Mini` display name |

**Slipped to W3:** formal `EvalRun` / `TaskResult` schemas; YAML task loader; ops metrics on every call; move runner into `evaluator/`.

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

## Rollout (amended after W2)

| When | Suites / work |
|------|----------------|
| **W3** | Eval schemas; `evaluator/` runner; IT support E2E; multi-model gateway |
| **W4–5** | Summarization, student study, policy Q&A; align **3-model pilot** with Track A |
| **W5–6** | Creative writing, research literature, med education, coding; dashboard charts |
| Later | Research workflow, variation overlay, benchmark subsets |

---

## Public benchmarks (reference)

| Benchmark | Use |
|-----------|-----|
| TruthfulQA MCQ | W2 spike only — optional column on label |
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
