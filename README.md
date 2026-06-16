# Security & QA Tools for Duke's AI Models

Code+ 2026 — Duke Office of Information Technology

Automated **nutrition labels** for Duke AI Gateway models: **security** (artifact scanning + inference safety) and **efficacy** (Duke judge suites + public benchmarks).

| Pillar | Question |
|--------|----------|
| **Scanning** | Can model files or dependencies compromise infrastructure? |
| **Safety** | Can the model be misused or violate policy at inference? |
| **Efficacy** | How well does it perform on Duke-relevant and standard tasks? |


---

## Where to go next

| I want to… | Start here |
|------------|------------|
| **Run the UI** on my machine | [Quick start](#quick-start) |
| **CLI** — scans, safety, eval, benchmarks, tests | [`docs/cli.md`](docs/cli.md) |
| **Docker model** (containerized UI, sibling jobs) | [`docs/docker.md`](docs/docker.md) |
| **Understand the system** (VM, DGX, ingest, Celery) | [`docs/architecture.md`](docs/architecture.md) |
| **Postgres schema and ingest** | [`docs/data-model.md`](docs/data-model.md) · [`dbutils/README.md`](dbutils/README.md) |
| **Track A** (scanning + safety) | [`docs/track-a-framework.md`](docs/track-a-framework.md) |
| **Track B** (evaluator + benchmarks) | [`docs/track-b-framework.md`](docs/track-b-framework.md) |
| **Gateway models and HF scan tiers** | [`docs/gateway-models.md`](docs/gateway-models.md) |
| **All documentation** | [`docs/README.md`](docs/README.md) |

**Pillar READMEs:** [`scanner/`](scanner/README.md) · [`safety/`](safety/README.md) · [`evaluator/`](evaluator/README.md) · [`benchmarks/`](benchmarks/README.md) · [`frontend/`](frontend/README.md) · [`gateway/`](gateway/README.md)

---

## Repository layout

```
scanner/       Track A — HF artifact scanning
safety/        Track A — promptfoo + garak red team
evaluator/     Track B — Duke LLM-as-judge suites
benchmarks/    Track B — public benchmarks (IFEval, TruthfulQA, …)
gateway/       Live gateway catalog
frontend/      Nutrition-label UI
docker/        Containerized UI for the application VM
dbutils/       Shared Postgres ingest helpers
docs/          Architecture, data model, frameworks
api/           Flask REST + workers (planned)
unit_tests/    Automated tests
```

Runtime outputs are gitignored (`scanner/output`, `safety/output`, `evaluator/results`, `benchmarks/results`).

---

## Quick start

```bash
git clone git@gitlab.oit.duke.edu:codeplus/security-and-qa-for-ai-models.git
cd security-and-qa-for-ai-models
uv sync
cp .env.example .env          # paste DUKE_GATEWAY_KEY from dashboard.ai.duke.edu
uv run flask --app frontend:create_app run --debug
# → http://127.0.0.1:5000
```

Dependencies: [`pyproject.toml`](pyproject.toml) + [`uv.lock`](uv.lock).

**Containerized UI** (application VM): `./docker/run.sh up --build`.
**All CLI commands:** [`docs/cli.md`](docs/cli.md).

---

## Environment

One repo-root [`.env.example`](.env.example) → `.env` (never commit). Key variables:

- `DUKE_GATEWAY_URL`, `DUKE_GATEWAY_KEY` — gateway chat and catalog (aliases: `OPENAI_*`)
- `HF_TOKEN` — gated Hugging Face downloads (scanning)
- `POSTGRES_DSN`, `EFFICACY_DB_DSN` — optional Postgres ingest and UI DB read paths
- `APP_PORT`, `FRONTEND_LAUNCH_MODE` — optional app UI tweaks

Host-specific values (user id, Docker socket group, repo path) are auto-detected by `./docker/run.sh`.

---

## Links

- [Code+ project page](https://codeplus.duke.edu/project/security-quality-assurance-tools-dukes-ai-models/)
- [GitLab](https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models)
- [Duke AI Suite](https://oit.duke.edu/ai-suite) · [Gateway dashboard](https://dashboard.ai.duke.edu)
