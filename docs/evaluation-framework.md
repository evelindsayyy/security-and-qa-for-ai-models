# Evaluation framework (Track B)

Reference for **Grace and Jack**. Track A: [`security-framework.md`](security-framework.md). Index: [`README.md`](README.md). Schedule: [`team-tracks.md`](team-tracks.md).

Track B implements task YAML under `tasks/` and `evaluator/`. This document lists **proposed task ideas**.

---

## Design principle

Duke-custom tasks are primary. Public benchmarks inform metrics and reference scores on the nutrition label.

```text
Layer 1     Duke task suites (Track B to implement in tasks/)
Layer 2     Adapted public benchmark subsets
Layer 3     Published external scores (reference only)
```

Every eval run should record operational metrics: latency, tokens, cost, failure rate.

---

## Proposed MVP task ideas (by audience)

One distinct task type per suite.

| Proposed suite | Audience | Task idea (scope) |
|----------------|----------|-------------------------|
| IT support | Staff, students | Duke technology and access (rubric draft exists in `tasks/rubrics/it_support.yaml`) |
| Policy Q&A | All | Institutional policy and procedures — not course content |
| Document summarization | All | Neutral long-form document to concise summary |
| Student study | Undergraduates | Explain concepts and problem-solving steps — not complete graded assignments |
| Creative writing | Students, humanities | Feedback on drafts and craft — not ghostwrite submissions |
| Research literature | Faculty, grad researchers | Abstract summary, critical appraisal, methods literacy |
| Research workflow | Faculty, grad, lab | Reproducibility, IRB awareness, authorship norms — not legal advice |
| Med education | Med students, biomedical grad | Pathophysiology and basic science from educational vignettes — not diagnosis or treatment |
| Coding snippet | Students, researchers, CoLab | Short code explanation or debug — not full repositories |
| Variation consistency | All | Cross-cutting: N rephrased prompts per intent (Charley Kneifel) |

### Ideas to avoid duplicating

| Keep separate | Reason |
|---------------|--------|
| Student study vs policy Q&A | Course learning vs Duke rules |
| Student study vs creative writing | Expository help vs prose style |
| Document summarization vs research literature | Generic docs vs scholarly papers |
| Research literature vs med education | General research vs clinical-science teaching |
| Research workflow vs policy Q&A | Research ops vs institutional policy |
| Coding snippet vs IT support | Programming vs accounts and licensing |
| Efficacy suites vs Track A safety | Quality scoring vs harm, jailbreaks, academic dishonesty |

Academic integrity prompts (e.g. "write my essay for me") belong in **Track A safety**, not efficacy.

---

## Suggested rollout (Track B)

| Phase | Suites to prioritize |
|-------|----------------------|
| Weeks 3–4 | IT support, document summarization, student study, policy Q&A |
| Weeks 4–6 | Creative writing, research literature, med education, coding snippet |
| Later | Research workflow, variation overlay, benchmark subsets |

---

## Public benchmarks (reference)

| Benchmark | Duke fit | Use |
|-----------|----------|-----|
| DocBench / QASPER | Researchers, staff | Summarization patterns |
| IFEval | All | Format compliance |
| MT-Bench / AlpacaEval | General chat | Quality reference |
| TruthfulQA / MMLU subset | Students, researchers | Factuality |
| Berkeley Function Calling | Agentic / research | Tool-use (ITSO context) |
| SWE-bench (full) | Low for gateway API | External reference only |
| SWE-bench Lite / HumanEval | CoLab, CS | Optional; overlaps coding snippet idea |
| HELM, Chatbot Arena | — | Reference scores on label |

Details: [`tasks/benchmarks/manifest.yaml`](../tasks/benchmarks/manifest.yaml) (benchmark catalog only).

---

## Metrics (for Track B to implement)

| Task family | Suggested metrics |
|-------------|-------------------|
| Summarization | ROUGE-L, LLM-as-judge |
| Q&A, study, research, med, policy | LLM-as-judge with per-suite rubrics |
| Creative writing | Judge on clarity, voice, tone |
| Coding snippet | Judge; optional execution check later |
| All | Latency, tokens, cost, failure rate |

---

## Out of scope (summer)

Full SWE-bench on gateway APIs; clinical patient advice in efficacy tasks; multilingual sweeps.

---

## Open decisions (Track B)

- Which MVP+ suite after core four: med education vs research literature
- License review for imported benchmark prompts
- Shared rubric template vs per-suite rubrics
