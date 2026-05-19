# Security & QA Tools for Duke's AI Models
### Code+ 2026 — Duke Office of Information Technology
> **Draft** — subject to change as scope is confirmed with stakeholders

---

## Overview

As Duke deploys more AI models locally for privacy and cost reasons, three problems emerge around tracking and validating those models:

1. **Security** — can a model do something nefarious to us? (compromise Duke's infrastructure, or the user's information)
2. **Safety** — does a model allow users to do something nefarious? (harmful content, policy violations)
3. **Efficacy** — how well does a model actually do the job asked of it? (performance across a variety of use cases)

This project builds the tooling to answer all three questions, with a shared dashboard that Duke IT teams can use to make informed decisions about AI model adoption.

---

## The Three Pillars

### 1. Security
Evaluates AI model artifacts downloaded from public repositories (primarily Hugging Face) before they touch Duke's systems. Happens at the file level, before a model is ever run. Checks include:
- Malicious code hidden in model files (pickle/deserialization exploits)
- Compromised or vulnerable dependencies
- Supply chain and provenance risks
- Exposed secrets or credentials in model repositories

Produces a structured risk report with an overall score and per-finding breakdown.

### 2. Safety
Evaluates model outputs at inference time to determine whether a model can be used to cause harm or violate Duke policy. Checks include:
- Harmful content generation (weapons, violence, self-harm)
- Academic dishonesty facilitation
- Sensitive information disclosure
- Resistance to jailbreaks and prompt injection

Produces a safety profile across hazard categories with pass/fail and severity ratings.

### 3. Efficacy
Benchmarks how well different models perform across Duke-relevant task categories and configurations. Checks include:
- IT support and helpdesk Q&A accuracy
- Document summarization quality
- Duke policy question answering
- Response latency and throughput
- Other usecases (yet to add)

Produces comparative analytics to help Duke OIT/users choose the right model for each use case.

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
- **Async jobs:** TBD (likely Celery + Redis)
- **Inference:** Duke AI Gateway via LiteLLM
- **Containerization:** Docker / Docker Compose
- **CI/CD:** GitLab CI
- **Dashboard:** TBD

---

## Repo Structure (High Level)

```
scanner/        # Pillar 1: Security — artifact scanning, pure Python
evaluator/      # Pillars 2+3: Safety + Efficacy — inference-time evaluation, pure Python
tasks/          # YAML task suite definitions (Duke-specific prompts and safety probes)
api/            # Web API layer wrapping all three pillars
frontend/       # Dashboard UI (stack TBD)
testing/        # Spike scripts and exploratory work
docs/           # Architecture, data model, API spec
```

See `docs/architecture.md` for system design and `docs/data-model.md` for DB schema (both in progress).

---

## Getting Started

> Full setup instructions will be added once the stack is finalized and Docker Compose is configured.

For now, to run the gateway test script:

```bash
cp .env.example .env
# Add your Duke AI Gateway API key to .env
pip install -r requirements.txt
python testing/test_gateway.py
```

---

## Environment Variables

See `.env.example` for all required variables. Never commit a real `.env` file.

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
| Stakeholder meeting | Pending |
| Stack finalized | Pending stakeholder meeting |
| Repo structure + CI | Week 2 |
| Security scanner MVP | Weeks 3–4 |
| Safety + efficacy evaluator MVP | Weeks 5–6 |
| Integration + deployment | Week 7 |
| Polish + handoff | Weeks 8–9 |

---

*This README will be updated as scope is confirmed and the project progresses.*