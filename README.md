# Security & QA Tools for Duke's AI Models
### Code+ 2026 — Duke Office of Information Technology
> **Draft** — subject to change as scope is confirmed with stakeholders

---

## Overview

As Duke deploys more AI models locally for privacy and cost reasons, two problems emerge: ensuring those models are safe to run on Duke infrastructure, and determining which ones actually perform best for Duke's specific use cases.

This project builds the tooling to answer both questions — a **security scanning framework** and a **model evaluation framework** — with a shared dashboard that Duke IT teams can use to make informed, defensible decisions about AI model adoption.

---

## The Two Pillars

### 1. Security Scanner
Automatically evaluates AI models downloaded from public repositories (primarily Hugging Face) before they touch Duke's systems. Checks include:
- Malicious code hidden in model files (pickle/deserialization exploits)
- Compromised or vulnerable dependencies
- Supply chain and provenance risks
- Exposed secrets or credentials

Produces a structured risk report with a score and per-finding breakdown.

### 2. Model Evaluator
Benchmarks how well different models perform across Duke-relevant task categories (IT support, document summarization, policy Q&A, etc.) and inference configurations. Produces comparative analytics to help Duke OIT choose the right model for each use case.

---

## Stakeholders

| Name | Role |
|---|---|
| Alex Merck, Nick Tripp | Duke IT Security Office (ITSO) — primary |
| David McAlpine | Research — TBD involvement |
| Vanessa Simmons, George Bowen | Project leads |

---

## Team

Grace Zhan · Raphael Karamagi · Jack Yi · Nithi Vechalapu 

---

## Tech Stack
> Partially confirmed — final decisions pending stakeholder meeting

- **Language:** Python 3.11+
- **API layer:** TBD (likely FastAPI)
- **Database:** TBD (likely PostgreSQL)
- **Inference:** Duke AI Gateway via LiteLLM
- **Containerization:** Docker / Docker Compose
- **CI/CD:** GitLab CI
- **Dashboard:** TBD

---

## Repo Structure (High Level)

```
scanner/        # Security scanning logic — pure Python
evaluator/      # Model evaluation logic — pure Python
tasks/          # YAML task suite definitions (Duke-specific prompts)
api/            # Web API layer wrapping both pillars
frontend/       # Dashboard UI (stack TBD)
testing/        # Scripts and exploratory work
docs/           # Architecture, data model, API spec
```

See `docs/architecture.md` for system design and `docs/data-model.md` for DB schema (both in progress).

---

## Getting Started

> Setup instructions will be added once the stack is finalized and Docker Compose is configured.

For now, to run the gateway test script:

```bash
cp .env.example .env
# Add your Duke AI Gateway API key to .env
pip install -r requirements.txt
python testing/test_gateway.py
```

---

## Environment Variables

See `.env.example` for all required variables. 

Key variables will include:
- `DUKE_GATEWAY_API_KEY` — Duke AI Gateway key from dashboard.ai.duke.edu
- `HUGGINGFACE_TOKEN` — HuggingFace Hub API token
- `DATABASE_URL` — PostgreSQL connection string (once DB is configured)

---

## Project Links

- Project page: https://codeplus.duke.edu/project/security-quality-assurance-tools-dukes-ai-models/
- GitLab repo: https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models
- Duke AI Suite: https://oit.duke.edu/ai-suite
- Duke AI Gateway: https://dashboard.ai.duke.edu

---

## Status

| Milestone | Status |
|---|---|
| Gateway API tested | Done |
| Stakeholder meeting | Scheduled / Pending |
| Stack finalized | Pending stakeholder meeting |
| Repo structure + CI | Week 2 |
| Scanner MVP | Weeks 3–4 |
| Evaluator MVP | Weeks 5–6 |
| Integration + deployment | ⏳ Week 7 |
| Polish + handoff | Weeks 8–9 |

---

*This README will be updated as scope is confirmed and the project progresses.*