# Team tracks and schedule

Code+ 2026 — Duke OIT. The nutrition label has two pillars — **security** (scanning + safety) and **efficacy**.

**Execution (tasks):** GitLab — [`.gitlab/README.md`](../.gitlab/README.md) (Track A, Track B, Team).

| Doc | Contents |
|-----|----------|
| [`track-a-framework.md`](track-a-framework.md) | Track A: scanning, safety |
| [`track-b-framework.md`](track-b-framework.md) | Track B: efficacy |
| [`gateway-models.md`](gateway-models.md) | Gateway + HF catalogs |
| [`data-model.md`](data-model.md) | Postgres schema (implemented tables) |
| [`architecture.md`](architecture.md) | System design |
| [`tool-stack.md`](tool-stack.md) | Tools |

---

## Tracks

| Track | Members | Delivers | Code |
|-------|---------|----------|------|
| **A — Scanning & Safety** | Raphael Karamagi, Nithi Vechalapu | **Security** pillar | `scanner/`, `safety/` |
| **B — Evaluation** | Grace Zhan, Jack Yi | **Efficacy** pillar | `evaluator/`, `tasks/` |

---

## Phases

Dated, step-by-step milestones live in the GitLab tracker; this is the high-level shape.

| Phase | Focus | Track A | Track B |
|-------|-------|---------|---------|
| Spikes | Scaffold, gateway smoke, data-model sketch | HF scan + tool research | Gateway smoke; TruthfulQA pilot |
| Pipelines | Docker stacks, catalog, `frontend/`, E2E on gateway models | `scanner/` pipeline; safety merge | `evaluator/` runner + judge; MVP suites + benchmarks |
| Persistence | Postgres ingest + UI read (all pillars); REST partial | scan/safety DB + API next | eval GET live; benchmark DB + API next |
| Full UI | `frontend/` reads `api/` | Scanning + safety views | Efficacy charts |
| Demo freeze | Representative catalog; documented limits | Gateway safety + HF samples | Gateway efficacy |

Shared: `frontend/`, `api/`, Postgres, GitLab CI.

---

## Deployment context

~35 cloud gateway models today; on-prem HF coming. ITSO: probes must match deployment type (chatbot vs agentic, tools, guardrails).

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
| B | LiteLLM, Duke YAML, ROUGE-L, LLM-as-judge, IFEval, TruthfulQA, MMLU, ToMi, consistency |

Details: [`tool-stack.md`](tool-stack.md).
