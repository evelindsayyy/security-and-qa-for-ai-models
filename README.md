# Security & QA Tools for Duke's AI Models
### Code+ 2026 — Duke Office of Information Technology
> **Draft** — subject to change

---

## Overview

As Duke deploys more AI models locally for privacy and cost reasons, three problems emerge around tracking and validating those models:

1. **Security** — can a model do something nefarious *to us*? (compromise Duke's infrastructure)
2. **Safety** — does a model allow users to do something nefarious? (harmful content, policy violations)
3. **Efficacy** — how well does a model actually do the job asked of it? (performance across Duke use cases)

This project builds the tooling to answer all three questions. The primary production use case is Duke's AI Gateway — the platform that publishes AI models to Duke's 40,000+ community members — which currently has no automated process for vetting models before they are published. This tool provides that missing piece, with a shared dashboard that Duke IT and AI Gateway teams can use to make informed, defensible decisions about AI model adoption.

The tool will eventually be designed to be generic enough for potential adoption by other institutions facing the same model vetting problem, but initially specific to Duke.

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
Benchmarks how well different models perform across Duke-relevant task categories and inference configurations. Checks include:
- IT support and helpdesk Q&A accuracy
- Document summarization quality
- Duke policy question answering
- Response latency and throughput

Produces comparative analytics to help Duke OIT choose the right model for each use case.

---

## Stakeholders

| Name | Role |
|---|---|
| Alex Merck, Nick Tripp | Duke IT Security Office (ITSO) — primary |
| Michael Faber | Duke AI Gateway / CoLab — primary |
| David McAlpine | Research — TBD involvement |
| Vanessa Simmons, George Bowen | Project leads |

---

## Team & Tracks

Development is split into two tracks. The nutrition label still reports all three pillars (security, safety, efficacy). See [`docs/team-tracks.md`](docs/team-tracks.md) for track ownership and the 10-week schedule.

| Track | Members | Focus |
|-------|---------|-------|
| **A — Security & Safety** | Raphael Karamagi, Nithi Vechalapu | Artifact scanning (Hugging Face), dependency CVEs, secrets; inference-time safety probes, jailbreaks, red teaming |
| **B — Evaluation** | Grace Zhan, Jack Yi | Efficacy benchmarks via Duke AI Gateway, task suites, metrics, operational performance (latency, cost, reliability) |

---

## Tech Stack
> Partially confirmed — final decisions pending stakeholder meeting

- **Language:** Python 3.11+
- **API layer:** TBD (likely FastAPI)
- **Database:** TBD (likely PostgreSQL)
- **Async jobs:** TBD (likely Celery + Redis — scanning and eval runs are long-running)
- **Inference:** Duke AI Gateway via LiteLLM (OpenAI-compatible)
- **Containerization:** Docker / Docker Compose
- **CI/CD:** GitLab CI
- **Dashboard:** TBD
- **Deployment target:** TBD — potentially GPU VM provisioned by Duke OIT

---

## Repo Structure (High Level)

```
scanner/        # Track A: Security — artifact scanning (Hugging Face, pre-deploy)
safety/         # Track A: Safety — inference-time probes, red teaming (gateway + on-prem)
evaluator/      # Track B: Evaluation — efficacy benchmarks via Duke AI Gateway
tasks/          # YAML task suites (efficacy prompts; safety probes under Track A coordination)
api/            # Web API layer wrapping all three pillars
frontend/       # Dashboard UI (stack TBD)
testing/        # Spike scripts and exploratory work
docs/           # Architecture, team tracks, data model, API spec
```

See `docs/team-tracks.md` (schedule), `docs/tool-stack.md` (tools), and `docs/architecture.md` (system design).

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
- `REDIS_URL` — Redis connection string (once async jobs are configured)

---

## Project Links

- Project page: https://codeplus.duke.edu/project/security-quality-assurance-tools-dukes-ai-models/
- GitLab repo: https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models
- Duke AI Suite: https://oit.duke.edu/ai-suite
- Duke AI Suite Models Guide: https://oit.duke.edu/help/articles/kb0038832/
- Duke AI Gateway dashboard: https://dashboard.ai.duke.edu

---

## Status

| Milestone | Status |
|---|---|
| Gateway API tested | Done |
| Stakeholder meeting — Alex + Nick (ITSO) | Pending |
| Stakeholder meeting — Michael Faber (AI Gateway) | Pending |
| Three-pillar framing confirmed | In progress |
| Stack finalized | Pending stakeholder meetings |
| GPU VM provisioned | Pending (George Bowen) |
| Repo structure + CI | Week 2 |
| Security & safety MVP (Track A) | Weeks 3–4 |
| Evaluation MVP (Track B) | Weeks 3–4 (parallel) |
| API layer + dashboard | Weeks 5–6 |
| Integration + deployment | Week 7 |
| Polish + handoff | Weeks 8–9 |
| Stretch goals (ML-BOM, scheduling, external packaging) | Week 10 |

---

*This README will be updated as scope is confirmed and the project progresses.*