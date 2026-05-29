# Team tracks and schedule

Code+ 2026 — Duke OIT. The nutrition label has two pillars — **security** (scanning + safety) and **efficacy**.

**Execution (tasks):** GitLab — [`.gitlab/README.md`](../.gitlab/README.md) (Track A, Track B, Team).

| Doc | Contents |
|-----|----------|
| [`track-a-framework.md`](track-a-framework.md) | Track A: scanning, safety, security pillar |
| [`gateway-models.md`](gateway-models.md) | Duke gateway catalog; HF scan list; test tiers |
| [`data-model.md`](data-model.md) | Postgres sketch; structured outputs |
| [`evaluation-framework.md`](evaluation-framework.md) | Track B task design |
| [`tool-stack.md`](tool-stack.md) | Tools and rationale |
| [`architecture.md`](architecture.md) | System design |

---

## Tracks

| Track | Members | Delivers | Code |
|-------|---------|----------|------|
| **A — Scanning & Safety** | Raphael Karamagi, Nithi Vechalapu | **Security** pillar (scanning + safety) | `scanner/`, `safety/` |
| **B — Evaluation** | Grace Zhan, Jack Yi | **Efficacy** pillar | `evaluator/`, `tasks/` |

| Label part | Track A component | Question |
|------------|-------------------|----------|
| Security → **Scanning** | `scanner/` | Files, deps, secrets |
| Security → **Safety** | `safety/` | Harm, policy, red team |
| **Efficacy** | `evaluator/` | Task performance |

---

## Deployment context

~10 cloud gateway models today; on-prem Hugging Face models coming. Store `deployment_context` per model (chatbot vs agentic, tools, guardrails). ITSO: safety and efficacy probes must match deployment type.

| Deployment | Scanning | Safety | Efficacy |
|------------|----------|--------|----------|
| Cloud gateway | Lower priority | Yes | Yes |
| OSS on-prem | Yes | Yes | Yes |
| Unknown HF repo | Yes | Yes | Optional |

---

## Tool summary

| Track | Stack |
|-------|--------|
| A — scanning | ModelScan, Fickling, pip-audit, OSV, TruffleHog |
| A — safety | garak, promptfoo, Duke probes |
| B | LiteLLM, Duke YAML suites, ROUGE-L, LLM-as-judge |

Details: [`tool-stack.md`](tool-stack.md).

---

## Weekly outcomes

Tasks live in GitLab. High-level goals:

| Week | Team | Track A (scanning & safety) | Track B (efficacy) |
|------|------|----------------------------|---------------------|
| 1 | Scaffold, architecture, gateway test | Tool research (done) | Gateway test (done) |
| 2 | Data model, catalog, Docker, CI, mockups | HF scan regression; gap map; SafetyResult; promptfoo on **1 gateway** model | Schemas; loader; gateway smoke |
| 3 | Structured output | scanner/ + safety/; safety on **1 gateway** model | Multi-model runner; IT support E2E |
| 4 | E2E + unit tests | Scan E2E; garak + promptfoo on **3 gateway** models | Core suites; align pilot models with Track A |
| 5 | **API, Celery, Postgres** | `/scans`, `/safety` | `/evals`, LLM-as-judge |
| 6 | **Dashboard** | Scanning + safety UI | Efficacy charts |
| 7 | Demo, **freeze** | Security pillar complete on gateway + HF samples | Gateway efficacy runs |
| 8 | Hardening | Scanning FP study ~50 HF models | Judge validation |
| 9 | Handoff | Limitations, ADRs | Eval limitations, runbooks |
| 10 | Stretch (1–2) | Optional scanning/safety extras | Optional suites / benchmarks |

Shared all weeks: `api/`, `frontend/`, Postgres, Celery, GitLab CI, nutrition label UI.
