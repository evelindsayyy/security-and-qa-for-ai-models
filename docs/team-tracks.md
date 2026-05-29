# Team tracks and schedule

Code+ 2026 — Duke OIT. The nutrition label has two pillars — **security** (scanning + safety) and **efficacy**.

**Execution (tasks):** GitLab — [`.gitlab/README.md`](../.gitlab/README.md) (Track A, Track B, Team).

| Doc | Contents |
|-----|----------|
| [`track-a-framework.md`](track-a-framework.md) | Track A: scanning, safety |
| [`track-b-framework.md`](track-b-framework.md) | Track B: efficacy |
| [`gateway-models.md`](gateway-models.md) | Gateway + HF catalogs |
| [`data-model.md`](data-model.md) | Postgres sketch |
| [`architecture.md`](architecture.md) | System design |
| [`tool-stack.md`](tool-stack.md) | Tools |

---

## Tracks

| Track | Members | Delivers | Code |
|-------|---------|----------|------|
| **A — Scanning & Safety** | Raphael Karamagi, Nithi Vechalapu | **Security** pillar | `scanner/`, `safety/` (W3+) |
| **B — Evaluation** | Grace Zhan, Jack Yi | **Efficacy** pillar | `evaluator/`, `tasks/` |

---

## Week 2 actuals (Friday)

| Area | Done | Carried to W3 |
|------|------|---------------|
| **Track A — scanning** | ModelScan, Fickling, combined scan, `ScanResult`; gpt2 / distilbert / opt-125m; OSV/pip-audit; Trivy spike | Gap map doc; `scanner/` package |
| **Track A — safety** | — | `SafetyResult`; promptfoo smoke; `safety/` package |
| **Track B** | TruthfulQA MCQ on 3 gateway models; LiteLLM utilities | `EvalRun` schemas; YAML loader; `evaluator/` |
| **Team** | Architecture + data-model docs | Docker Compose, CI, catalog seed, mockups |

Detail: [`track-a-framework.md`](track-a-framework.md), [`track-b-framework.md`](track-b-framework.md). GitLab paste source: local `gitlab-transfer.md`.

---

## Weekly outcomes (amended)

| Week | Team | Track A | Track B |
|------|------|---------|---------|
| 1 | Scaffold | Tool research ✓ | Gateway test ✓ |
| **2** | Data model docs | Scan spike ✓; safety schemas ✗ | TruthfulQA pilot ✓; formal schemas ✗ |
| **3** | Docker, CI, catalog | `scanner/` + `safety/`; 1-model safety | `evaluator/`; IT support E2E |
| 4 | E2E tests | Scan E2E; safety **3 models** | Core suites; same 3 models |
| 5 | Postgres + API | `/scans`, `/safety` | `/evals` |
| 6 | Dashboard | Scanning + safety UI | Efficacy charts |
| 7 | Demo freeze | Full gateway safety + HF samples | Gateway efficacy |
| 8–9 | Hardening / handoff | FP study | Judge validation |
| 10 | Stretch | Optional | Optional |

Shared: `api/`, `frontend/`, Postgres, Celery, GitLab CI.

---

## Deployment context

~10 cloud gateway models today; on-prem HF coming. ITSO: probes must match deployment type (chatbot vs agentic, tools, guardrails).

| Deployment | Scanning | Safety | Efficacy |
|------------|----------|--------|----------|
| Cloud gateway | N/A (no HF repo) | Yes | Yes |
| OSS on-prem | Yes | Yes | Yes |

---

## Tool summary

| Track | Stack |
|-------|--------|
| A — scanning | ModelScan, Fickling, pip-audit, OSV, TruffleHog |
| A — safety | garak, promptfoo, Duke probes |
| B | LiteLLM, Duke YAML, ROUGE-L, LLM-as-judge |

Details: [`tool-stack.md`](tool-stack.md).
