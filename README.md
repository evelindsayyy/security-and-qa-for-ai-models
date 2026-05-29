# Security & QA Tools for Duke's AI Models

Code+ 2026 — Duke Office of Information Technology

---

## Overview

Duke's AI Gateway publishes models to 40,000+ community members but lacks automated vetting before publication. This project produces a **nutrition label** per model across three pillars:

| Pillar | Question |
|--------|----------|
| **Security** | Can model files or dependencies compromise Duke infrastructure? |
| **Safety** | Can the model be used to cause harm or violate policy at inference time? |
| **Efficacy** | How well does the model perform on Duke-relevant tasks (IT support, coursework help, research, med education, creative writing, summarization, and related MVP suites)? |

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
| **A — Security & Safety** | Raphael Karamagi, Nithi Vechalapu | HF artifact scanning, CVEs, secrets; safety probes, red teaming |
| **B — Evaluation** | Grace Zhan, Jack Yi | Efficacy benchmarks, task suites, metrics, operational performance |

Details: [`docs/team-tracks.md`](docs/team-tracks.md) · [`docs/security-framework.md`](docs/security-framework.md) (Track A) · [`docs/evaluation-framework.md`](docs/evaluation-framework.md) (Track B)

---

## Deployment context

| Today | Coming |
|-------|--------|
| ~10 Azure/OpenAI models on AI Gateway (cloud, guardrails) | On-prem GPU hosting of open-source Hugging Face models |
| Efficacy and safety probes are highest priority | File-level security scanning becomes critical pre-deploy |

Evaluation is **deployment-aware** (chatbot vs agentic, tools, data access, guardrails, commercial vs OSS). See ITSO notes in [`docs/team-tracks.md`](docs/team-tracks.md).

---

## Repository layout

```
scanner/        # Track A: artifact security (Hugging Face)
safety/         # Track A: inference-time safety probes
evaluator/      # Track B: efficacy evaluation via AI Gateway
tasks/          # YAML task suites and rubrics
api/            # FastAPI (planned)
frontend/       # Dashboard (planned, React per mockups)
testing/        # Spikes (gateway test, security scanning on DGX)
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
# Set DUKE_GATEWAY_API_KEY from dashboard.ai.duke.edu
pip install -r requirements.txt
python testing/test_gateway.py
```

**Security scanning spike (DGX, Docker only):**

```bash
cd testing/security_scanning_tests
# See README in that directory for UID/GID and docker compose steps
```

---

## Environment variables

See `.env.example`. Never commit `.env`.

- `DUKE_GATEWAY_API_KEY` — Duke AI Gateway
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
| Data model + GitLab CI | Week 2 (in progress) |
| Scanner + safety MVP | Weeks 3–4 |
| Evaluation MVP | Weeks 3–4 |
| API + persistence | Week 5 |
| Dashboard + DGX deploy | Week 6 |
| Stakeholder demo, scope freeze | Week 7 |
