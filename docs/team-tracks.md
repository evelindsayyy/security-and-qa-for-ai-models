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

## Weekly outcomes 

| Week | Focus | Track A | Track B |
|------|------|---------|---------|
| 1 | Scaffold | Tool research | Gateway test |
| 2 | scan/eval spikes, `docs/data-model.md` sketch, gateway doc | HF scan spike; TruthfulQA pilot | Gateway smoke |
| 3 | Docker, CI, catalog, `frontend/` | `scanner/` + `safety/`; 1-model safety | `evaluator/`; MVP suites, 1 gateway model |
| 4 | E2E tests; frontend stubs | Scan E2E; safety 3 models | MVP suites on 3 pilot models |
| 5 | Postgres + `api/` | `/scans`, `/safety` | `/evals` |
| 6 | `frontend/` full UI | Scanning + safety views | Efficacy charts |
| 7 | Demo freeze | Full gateway safety + HF samples | Gateway efficacy |
| 8–9 | Hardening / handoff | FP study | Judge validation |
| 10 | Stretch | Optional | Optional |

Shared: `frontend/`, `api/` (W5+), Postgres, Celery, GitLab CI.

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
| A — scanning | ModelScan, Fickling, ModelAudit, pip-audit, OSV, TruffleHog |
| A — safety | garak, promptfoo, Duke probes |
| B | LiteLLM, Duke YAML, ROUGE-L, LLM-as-judge |

Details: [`tool-stack.md`](tool-stack.md).
