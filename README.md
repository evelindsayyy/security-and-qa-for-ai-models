# Security & QA Tools for Duke's AI Models

Code+ 2026 — Duke Office of Information Technology

---

## Overview

Duke's AI Gateway publishes models to 40,000+ community members but lacks automated vetting before publication. This project produces a **nutrition label** per model across two pillars:

| Pillar | Part | Question |
|--------|------|----------|
| **Security** | **Scanning** | Can model files or dependencies compromise Duke infrastructure? |
| **Security** | **Safety** | Can the model be used to cause harm or violate policy at inference time? |
| **Efficacy** | | How well does the model perform on Duke-relevant tasks (IT support, coursework help, research, med education, creative writing, summarization, and related MVP suites)? |

**Track A** (scanning + safety) delivers the **security** pillar. **Track B** delivers **efficacy**.

Deliverable: structured, publishable results for OIT and the AI Gateway — depth on ~10 gateway models today, with a path to on-prem open-source models later.

---

## Stakeholders

| Name | Role | Engagement |
|------|------|------------|
| Charley Kneifel | CTO, Duke OIT | Executive sponsor; variation-testing input |
| Michael Faber | AI Gateway / Innovation Co-Lab | Primary product user; nutrition label for OIT site |
| Alex Merck, Nick Tripp | Duke IT Security Office (ITSO) | Threat model, deployment-context requirements |
| Michael Roman | ITSO (via Alex) | Security coordination |
| Vanessa Simmons, George Bowen | Code+ project leads | Oversight and infrastructure |

---

## Team and tracks

| Track | Members | Focus |
|-------|---------|-------|
| **A — Scanning & Safety** | Raphael Karamagi, Nithi Vechalapu | Security pillar: HF scanning, CVEs, secrets; inference safety and red team |
| **B — Evaluation** | Grace Zhan, Jack Yi | Efficacy benchmarks, task suites, metrics, operational performance |

Docs: [`docs/README.md`](docs/README.md) · Track A: [`docs/track-a-framework.md`](docs/track-a-framework.md) · Track B: [`docs/track-b-framework.md`](docs/track-b-framework.md)

**Planning:** GitLab — [`.gitlab/README.md`](.gitlab/README.md) (how to use issues); technical detail in `docs/`

---

## Deployment context

| Today | Coming |
|-------|--------|
| ~10 **gateway** models (Azure/OpenAI/Meta cloud APIs — see [`docs/gateway-models.md`](docs/gateway-models.md)) | On-prem HF hosting (then **scanning** + safety on those repos) |
| **Safety** and efficacy run against gateway IDs via LiteLLM | **Scanning** on HF artifacts before deploy |
| Mistral phased out — exclude from new tests | Confirm catalog with OIT |

Evaluation is **deployment-aware** (chatbot vs agentic, tools, data access, guardrails, commercial vs OSS). See ITSO notes in [`docs/team-tracks.md`](docs/team-tracks.md).

---

## Repository layout

```
scanner/        # Track A: scanning (HF artifacts)
safety/         # Track A: safety (inference / red team)
evaluator/      # Track B: efficacy evaluation via AI Gateway
tasks/          # YAML task suites and rubrics
api/            # FastAPI (planned)
frontend/       # Dashboard (planned, React per mockups)
testing/        # Spikes: scanning/, eval/, gateway/
docs/           # See docs/README.md
```

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Inference | LiteLLM to Duke AI Gateway (OpenAI-compatible) |
| Security spike | ModelScan, Fickling, pip-audit, OSV API |
| Containers | Docker Compose on DGX (`asus-dgx-04.oit.duke.edu`) |
| API / DB / jobs | FastAPI, PostgreSQL, Celery + Redis (weeks 5+) |
| Dashboard | Next.js + Tailwind (week 6, per Grace mockups) |
| CI | GitLab CI |

Tool matrix: [`docs/tool-stack.md`](docs/tool-stack.md)

---

## Documentation

See [`docs/README.md`](docs/README.md) for the full index.

---

## Getting started

**Gateway test (host or container):**

```bash
cp .env.example .env
# Set OPENAI_API_KEY / DUKE_AI_GATEWAY_API_KEY from dashboard.ai.duke.edu
pip install -r requirements.txt
python testing/test_gateway.py
```

**TruthfulQA pilot (Track B):**

```bash
export DUKE_AI_GATEWAY_API_KEY=...
cd testing/eval/truthfulqa
python evaluate_truthfulqa_mcq.py --limit 50
```

**Security scanning spike (DGX, Docker only):**

```bash
cd testing/scanning
# See README in that directory for UID/GID and docker compose steps
```

---

## Environment variables

See `.env.example`. Never commit `.env`.

- `DUKE_AI_GATEWAY_API_KEY` / `OPENAI_API_KEY` — Duke AI Gateway (same token; see `.env.example`)
- `HUGGINGFACE_TOKEN` — Hugging Face Hub (gated models)
- `DATABASE_URL`, `REDIS_URL` — when API stack is live

---

## Links

- [Code+ project page](https://codeplus.duke.edu/project/security-quality-assurance-tools-dukes-ai-models/)
- [GitLab repository](https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models)
- [Duke AI Suite](https://oit.duke.edu/ai-suite)
- [AI Gateway dashboard](https://dashboard.ai.duke.edu)

---

## Status

| Milestone | Status |
|-----------|--------|
| Stakeholder calls (Charley, Michael Faber) | Done |
| ITSO call (Alex, Nick) | Done |
| Gateway API test | Done |
| Security scanning spike (ModelScan, Fickling, OSV/pip-audit) | Done |
| Track / tool / evaluation docs | Done |
| Week 2 scanning spike + TruthfulQA pilot | Done (see local `gitlab-transfer.md` W2) |
| Safety schemas + promptfoo; Team Docker/CI | Week 3 |
| Scanner + safety packages | Weeks 3–4 |
| Evaluation (`evaluator/`) MVP | Weeks 3–5 |
| API + persistence | Week 5 |
| Dashboard + DGX deploy | Week 6 |
| Stakeholder demo, scope freeze | Week 7 |
