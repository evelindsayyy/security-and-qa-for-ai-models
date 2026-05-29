# Team tracks and schedule

Code+ 2026 — Duke OIT. Nutrition label: **security**, **safety**, **efficacy**. Two dev tracks.

Docs: [`README.md`](README.md) · [`architecture.md`](architecture.md) · [`security-framework.md`](security-framework.md) · [`evaluation-framework.md`](evaluation-framework.md) · [`tool-stack.md`](tool-stack.md)

---

## Tracks

| Track | Members | Owns | Code |
|-------|---------|------|------|
| **A — Security & Safety** | Raphael Karamagi, Nithi Vechalapu | Artifact scan, safety / red team | `scanner/`, `safety/` |
| **B — Evaluation** | Grace Zhan, Jack Yi | Efficacy suites, gateway runner, ops metrics | `evaluator/`, `tasks/` |

| Pillar | Track |
|--------|-------|
| Security (files) | A |
| Safety (outputs) | A |
| Efficacy | B |

---

## Deployment context

**Now:** ~10 cloud gateway models. Track B primary for OIT; Track A runs safety on gateway. File scan lower priority until on-prem OSS.

**Soon:** On-prem HF models — Track A file scan required before deploy.

Store `deployment_context` per model (chatbot vs agentic, tools, guardrails). ITSO: eval and safety probes must match deployment type.

| Deployment | A | B |
|------------|---|---|
| Cloud gateway | Safety | Efficacy |
| OSS on-prem | Scan + safety | Efficacy |
| Unknown HF repo | Scan + safety | Optional |

---

## Tool stack (summary)

| Track | Stack |
|-------|--------|
| A | **Security:** ModelScan, Fickling, pip-audit, OSV, TruffleHog. **Safety:** garak, Duke probes |
| B | LiteLLM, Duke YAML, ROUGE-L, LLM-as-judge; optional benchmark subsets |
| Shared | LiteLLM → Duke AI Gateway |

Not used (summer): PyRIT, promptfoo (A), LLM Guard, ART, Watchtower — see [`tool-stack.md`](tool-stack.md).

---

## 10-week schedule

### Week 1 — Done

Repo scaffold; architecture draft; gateway test (`testing/test_gateway.py`); Track A tool research.

### Week 2 — Current

| Team | Problem statement; data model + `deployment_context`; Docker Compose; GitLab CI; label mockups |
| A | File-scan spike done. **Remaining:** gap map; `SafetyResult` schema; guardrail path (doc) |
| B | Task YAML + evaluator; ideas in `evaluation-framework.md` |

### Week 3

| Team | Structured output from gateway or HF data |
| A | Merged `ScanResult`; risk scorer; garak + Duke probe runner; start `scanner/`, `safety/` |
| B | Multi-model runner; task loader; ROUGE-L; variation testing |

### Week 4

| Team | E2E per track; unit tests |
| A | Deps + secrets in pipeline; garak pilot on gateway; `ScanResult` e2e |
| B | Core Duke suites; optional IFEval/DocBench subset; ops metrics |

### Week 5

REST API; Celery jobs; Postgres. `POST/GET /scans`, `/safety`, `/evals`; nutrition label endpoint; LiteLLM guardrail doc.

### Week 6

Dashboard on DGX; security drill-down; safety heatmap; efficacy charts.

### Week 7

Demo all gateway models; **feature freeze**; known-gaps doc.

### Week 8

Hardening; HF false-positive study (~50 models); judge validation (target r > 0.7).

### Week 9

Handoff; limitations doc; ADRs; CI notes.

### Week 10 — Stretch (pick 1–2)

CycloneDX ML-BOM; PyRIT multi-turn campaigns; scheduled CVE re-scan; LiteLLM guardrail prototype; GitLab scan on model release.

---

## Shared (all weeks)

`api/`, `frontend/`, Postgres, Celery + Redis, GitLab CI, nutrition label UI, week 7 demo. Spike until migrated: `testing/security_scanning_tests/`.
