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

Docs: [`docs/README.md`](docs/README.md) · Track A: [`docs/track-a-framework.md`](docs/track-a-framework.md) · Track B: [`docs/track-b-framework.md`](docs/track-b-framework.md) · GitLab: [`.gitlab/README.md`](.gitlab/README.md)

**Planning:** GitLab — [`.gitlab/README.md`](.gitlab/README.md); technical direction in `docs/`

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
scanner/        # Track A: scanning package (HF artifacts)
safety/         # Track A: safety (inference / red team)
evaluator/      # Track B: efficacy evaluation via AI Gateway
tasks/          # YAML task suites and rubrics
models/         # Gateway catalog seed placeholder (week 3+)
api/            # Flask REST API (week 5+)
frontend/       # Nutrition label UI (Flask W3+)
unit_tests/     # Automated unit tests 
testing/        # Manual gateway/eval spikes; scanning → scanner/
docs/           # See docs/README.md
```

Runtime data is gitignored (`scanner/models`, `scanner/output`, `testing/eval/output`, `instance/`). Each has a README so the path is documented.

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Inference | LiteLLM to Duke AI Gateway (cloud/API models); DCC SLURM for open-source weights (planned) |
| Security scanning | ModelScan, Fickling, ModelAudit (content-routed), pip-audit + OSV, TruffleHog |
| Safety / red team | garak, promptfoo, Duke policy probes (`safety/`) |
| Containers | Docker Compose on DGX (`asus-dgx-04.oit.duke.edu`) |
| API / DB / jobs | Flask, PostgreSQL, Celery + Redis (weeks 5+) |
| UI | `frontend/` — Flask (W3+), full label W6 (mockups) |
| CI | GitLab CI |

Tool matrix: [`docs/tool-stack.md`](docs/tool-stack.md)

---

## Documentation

See [`docs/README.md`](docs/README.md) for the full index.

---

## Getting started

**Frontend (Flask):**

```bash
uv sync
uv run flask --app frontend:create_app run --debug
# or: python main.py  →  /  /dashboard  /models
```

See [`frontend/README.md`](frontend/README.md).

**Gateway test (host or container):**

```bash
cp .env.example .env
# Set OPENAI_API_KEY / DUKE_AI_GATEWAY_API_KEY from dashboard.ai.duke.edu
pip install -r requirements.txt
python testing/test_gateway.py
```


**Scanner unit test (host, no Docker):**

```bash
uv run python -m unittest unit_tests.test_risk_scorer -v
```

**HF scanning (DGX/VM, Docker only):**

```bash
cd scanner/docker
cp .env.example .env && sed -i "s/^UID=.*/UID=$(id -u)/" .env && sed -i "s/^GID=.*/GID=$(id -g)/" .env
docker compose build
docker compose run --rm scanner python -m scanner scan gpt2
```

See [`scanner/README.md`](scanner/README.md). Spikes: [`scanner/experiments/`](scanner/experiments/).

**Safety red-team (gateway model, Docker):**

```bash
./safety/run_safety.sh "GPT 4.1 Mini"   # promptfoo policy + red-team + garak, then merge
# → safety/output/gpt-4.1-mini/merged_safety_result.json  (frontend: /safety)
```

See [`safety/README.md`](safety/README.md).

**Efficacy run (gateway model):**

```bash
uv run python evaluator/runner.py --candidate-model "GPT 4.1 Mini" --judge-model "Llama 4 Maverick"
# → evaluator/results/<timestamp>_<suite>_<model>.jsonl  (frontend: /eval-run)
```

See [`evaluator/README.md`](evaluator/README.md).

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
| Scanning spikes + TruthfulQA pilot | Done |
| Scanner package (3-tool + pip-audit/OSV + TruffleHog) | Done (W3–4) |
| Safety package (garak + promptfoo + Duke probes, merged) | Done (W3–4) |
| Evaluator (`evaluator/` runner + rubric judge) | Done (W3–4); multi-model pilot ongoing |
| API + persistence (JSON → Postgres ingest) | Week 5 |
| Dashboard + VM/DCC deploy | Week 6 |
| Stakeholder demo, scope freeze | Week 7 |
