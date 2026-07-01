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
| **Run the UI** | [Quick start](#quick-start) |
| **CLI and JSON API** — scans, safety, eval, benchmarks, tests | [`docs/cli.md`](docs/cli.md) · [`api/README.md`](api/README.md) |
| **Docker model** (UI + pillar jobs) | [`docs/docker.md`](docs/docker.md) · [`docker/`](docker/) |
| **Understand the system** (VM, Postgres, background jobs) | [`docs/architecture.md`](docs/architecture.md) |
| **Postgres schema and ingest** | [`docs/data-model.md`](docs/data-model.md) · [`dbutils/README.md`](dbutils/README.md) |
| **Authentication (OIDC, public/private views)** | [`auth/README.md`](auth/README.md) |
| **HTTPS / TLS (production Caddy)** | [`docker/README.md`](docker/README.md) |
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
auth/          Duke OIDC login, sessions, allowlist
frontend/      Nutrition-label UI
docker/        Containerized UI for the application VM
dbutils/       Shared Postgres ingest helpers
docs/          Architecture, data model, frameworks
api/           Flask REST under /api (reads + job POST); see api/README.md
unit_tests/    Automated tests
```

Runtime outputs are gitignored (`scanner/output`, `safety/output`, `evaluator/results`, `benchmarks/results`).

---

## Quick start

Default path: **containerized UI** (`python3 main.py` or `./docker/run.sh`) with pillar jobs in Docker. Host needs `uv` for setup commands only; Flask runs in the web container.

### One-time setup

```bash
git clone git@gitlab.oit.duke.edu:codeplus/security-and-qa-for-ai-models.git
cd security-and-qa-for-ai-models
uv sync --group dev              # core + psycopg + pytest/ruff (schema apply, ingest, tests)
cp .env.example .env             # paste DUKE_GATEWAY_KEY from dashboard.ai.duke.edu
./docker/build-pillars.sh        # build scanner, safety, evaluator, benchmark images
```

Requires Docker and Docker Compose. Pillar dependency groups (`scanner`, `safety`, `benchmarks`) aren't installed on the host.

### Optional — Postgres

When `POSTGRES_DSN` is set; Set `EFFICACY_DB_DSN` to the same value. Runs auto-sync to Postgres by default; set `AUTO_INGEST=0` to disable.

```bash
./scripts/apply-schemas.sh --bootstrap
# Auth backfill (after schema apply): uv run python db/migrate_auth_columns.py --apply
# Or one file: uv run python -m dbutils.apply_schema scanner/db/scan_schema.sql
```

### Run 

```bash
python3 main.py                   # foreground; same as ./docker/run.sh up --build
# Or: ./docker/run.sh up -d --build for background
# → http://127.0.0.1:5000
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
```

Use **Start** on `/scans/new`, `/safety/new`, `/eval-run/new`, or `/benchmarks/new`. Full CLI and API: [`docs/cli.md`](docs/cli.md) · [`api/README.md`](api/README.md).

### Alternative — host Flask (development)

For UI-only iteration without containerizing the app (pillar jobs still use Docker by default):

```bash
uv sync --group dev
cp .env.example .env
uv run python main.py --host           # dev Flask on APP_PORT (default 5000)
```

See [`frontend/README.md`](frontend/README.md) for API curl examples.

### Optional — pillar CLI on the host

Only if you run a pillar **without** Docker. Groups `scanner`, `safety`, and `benchmarks` **conflict** — install **at most one** with dev:

```bash
uv sync --group dev --group scanner      # OR --group safety OR --group benchmarks
```

Dependencies: [`pyproject.toml`](pyproject.toml) + [`uv.lock`](uv.lock).

---

## Environment

One repo-root [`.env.example`](.env.example) → `.env` (never commit). Key variables:

- `DUKE_GATEWAY_URL`, `DUKE_GATEWAY_KEY` — gateway chat and catalog (aliases: `OPENAI_*`)
- `HF_TOKEN` — gated Hugging Face downloads (scanning)
- `POSTGRES_DSN`, `EFFICACY_DB_DSN` — Postgres (set both to the same DSN); UI/API read DB when reachable
- `AUTH_ENABLED`, `DUKE_OIDC_*`, `AUTH_ALLOWED_NETIDS` — optional OIDC; see [`auth/README.md`](auth/README.md)
- `APP_PORT` — containerized UI port (default 5000 via `./docker/run.sh`)
- `FRONTEND_LAUNCH_MODE` — defaults to `docker` for Start buttons; set `host` for legacy dev

Host-specific values (user id, Docker socket group, repo path) are auto-detected by `./docker/run.sh` and `./docker/build-pillars.sh`.

---

## Links

- [Code+ project page](https://codeplus.duke.edu/project/security-quality-assurance-tools-dukes-ai-models/)
- [GitLab](https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models)
- [Duke AI Suite](https://oit.duke.edu/ai-suite) · [Gateway dashboard](https://dashboard.ai.duke.edu)
