# Team tracks and schedule

Code+ 2026 — Duke OIT. The **nutrition label** has three pillars (security, safety, efficacy). Development is split into **two tracks**.

Related: [`tool-stack.md`](tool-stack.md) · [`architecture.md`](architecture.md)

---

## Tracks

| Track | Members | Owns | Code |
|-------|---------|------|------|
| **A — Security & Safety** | Raphael Karamagi, Nithi Vechalapu | HF artifact scanning, dependency CVEs, secrets; inference safety (probes, jailbreaks, red team) | `scanner/`, `safety/` |
| **B — Evaluation** | Grace Zhan, Jack Yi | Efficacy benchmarks, gateway runner, task suites, metrics, ops performance | `evaluator/`, `tasks/` |

| Pillar | Track |
|--------|-------|
| Security (files) | A |
| Safety (outputs) | A |
| Efficacy (performance) | B |

---

## Duke deployment context

**Today:** ~10 Azure/OpenAI gateway models (cloud, contract guardrails). Track B (efficacy) is the primary OIT need. Track A still runs safety probes on gateway models. File scanning is lower priority until on-prem OSS.

**Soon:** On-prem GPU deployment of open-source Hugging Face models. Track A file scanning becomes critical before models touch Duke infrastructure.

**ITSO:** Evaluation must reflect deployment context — chatbot vs agentic, tools, data access, guardrails, commercial vs OSS. Store as `deployment_context` on each model.

| Deployment | Track A | Track B |
|------------|---------|---------|
| Cloud gateway (guarded) | Safety, red team | Efficacy (primary) |
| OSS on-prem | Security scan + safety | Efficacy |
| Unknown HF repo | Security scan + safety | Optional |

---

## Tool stack (summary)

| Track | Primary |
|-------|---------|
| A | ModelScan, Fickling, pip-audit, OSV, TruffleHog; LLM Guard and promptfoo (evaluate); LiteLLM for probes |
| B | LiteLLM, ROUGE-L, LLM-as-judge, efficacy YAML |
| Shared | LiteLLM to Duke AI Gateway |

Evaluate: OWASP Dependency-Check, Watchtower. Stretch: CycloneDX ML-BOM, LiteLLM guardrail hooks. Out of scope: Checkmarx, vulnhuntr (summer).

Details: [`tool-stack.md`](tool-stack.md)

---

## 10-week schedule

### Week 1 — Complete

| | Deliverables |
|---|--------------|
| **Team** | Repo scaffold; stakeholder calls (Charley, Michael); `docs/architecture.md`; gateway test |
| **Track A** | Tool research (ModelScan, Fickling); architecture draft |
| **Track B** | `testing/test_gateway.py` working against Duke AI Gateway |

---

### Week 2 — Current

| | Deliverables |
|---|--------------|
| **Team** | Problem statement in `docs/`; data model sketch with `deployment_context`; Docker Compose (API + DB + worker target); GitLab CI (lint, docker build); nutrition label layout (Grace mockups) |
| **Track A** | File-scan spike on DGX (done: modelscan, fickling, combined JSON, OSV vs pip-audit, metadata listing, Pydantic schemas, isolation notes, gpt2 calibration doc). Remaining: ModelScan gap map; scope lock; tool decisions; LiteLLM guardrail path (doc); safety probe YAML stub; `SafetyResult` schema |
| **Track B** | Nutrition label efficacy/ops fields; LiteLLM runner with timeout; first efficacy YAML tasks; DGX end-to-end; `EvalRun` / `TaskResult` schemas; variation-testing prior art |

---

### Week 3

| | Deliverables |
|---|--------------|
| **Team** | Both tracks produce structured output from real gateway or HF data |
| **Track A** | ModelScan + fickling reconciled into one `ScanResult`; format detector (safetensors vs pickle vs ONNX); initial risk scorer (tool disagreement handling); safety probe runner on gateway; begin `scanner/` and `safety/` extraction from spike |
| **Track B** | Multi-model, multi-task runner; YAML task loader; ROUGE-L; variation-testing pipeline (N rephrased prompts) |

---

### Week 4

| | Deliverables |
|---|--------------|
| **Team** | End-to-end pipelines per track; unit tests |
| **Track A** | Dependency scanning (pip-audit + OSV) in pipeline; TruffleHog for secrets; risk formula (low/medium/high/critical, NIST AI RMF language); model ID in, `ScanResult` JSON out; red-team probe design (prompt injection, jailbreaks); LLM Guard / promptfoo pilot results |
| **Track B** | Efficacy suites across Duke use cases; operational metrics (latency, tokens, cost, failure rate); side-by-side comparator; runner and metrics tests |

---

### Week 5

| | Deliverables |
|---|--------------|
| **Team** | REST API, background jobs, Postgres persistence |
| **Track A** | `POST/GET /scans`; `POST/GET /safety` (or combined safety endpoint); scan jobs via Celery |
| **Track B** | `POST/GET /evals`; LLM-as-judge scoring; eval jobs via Celery |
| **Team** | Nutrition label API endpoint (all pillars); document LiteLLM guardrail integration path |

---

### Week 6

| | Deliverables |
|---|--------------|
| **Team** | Dashboard on DGX; production Docker Compose |
| **Track A** | Security findings drill-down; safety heatmap (Grace mockup alignment) |
| **Track B** | Efficacy comparison charts; quality suite matrix |
| **Team** | Nutrition label as publishable view; commercial vs OSS visible in UI |

---

### Week 7 — Demo and scope freeze

| | Deliverables |
|---|--------------|
| **Team** | Run against all Duke gateway models; demo to stakeholders; triage feedback; **feature freeze** for weeks 8–9 |
| **Track A** | Gateway safety results; HF scan samples where applicable; red-team summary |
| **Track B** | Gateway efficacy results; LLM-as-judge vs human correlation reported |
| **Team** | Document known gaps before stakeholders ask |

---

### Week 8

| | Deliverables |
|---|--------------|
| **Team** | Hardening; performance and API security pass |
| **Track A** | False-positive study (~50 HF models); calibrate from gpt2 baseline |
| **Track B** | Judge validation on human-scored sample (target r > 0.7) |
| **Team** | Fix demo feedback |

---

### Week 9

| | Deliverables |
|---|--------------|
| **Team** | Handoff package (deploy, maintain, extend); limitations doc; final demo prep |
| **Track A** | Document scanner coverage limits (skipped files, poisoned weights, obfuscation) |
| **Track B** | Document eval limits (long-context, multilingual, multi-turn) |
| **Team** | ADRs for major design choices; CI/CD integration notes |

---

### Week 10 — Stretch (pick 1–2)

| Option | Track |
|--------|-------|
| CycloneDX ML-BOM generation | A |
| Red teaming pipeline formalization | A |
| Scheduled re-scanning (CVE feeds) | A |
| LiteLLM guardrail hook prototype | A |
| MCP/agent inventory doc | A |
| GitLab CI snippet for auto-scan on model release | Team |

---

## Shared ownership (all weeks)

- `api/`, `frontend/`, PostgreSQL schema, Celery + Redis, GitLab CI
- Nutrition label layout; week 7 demo
- Spike code: `testing/security_scanning_tests/` (Track A, until migrated to `scanner/`)
