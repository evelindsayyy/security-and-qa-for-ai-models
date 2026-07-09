# AGENTS.md — onboarding

Concise map for humans and agents working in this repo. Public docs: [`README.md`](README.md) → [`docs/`](docs/README.md). Pillar READMEs live next to each package.

## Pillars

| Area | Track | Role |
|------|-------|------|
| `scanner/` | A | HF artifact scan → `scan_result.json` → Postgres |
| `safety/` | A | garak + promptfoo → `MergedSafetyResult` → Postgres |
| `evaluator/` | B | LLM-as-judge suites → JSONL → Postgres |
| `benchmarks/` | B | Public benchmarks → results → Postgres |
| `gateway/` | Shared | LiteLLM catalog |
| `frontend/` | Shared | Flask UI; Postgres when DSN set; browser launchers |
| `api/` | Shared | REST GET/POST per pillar + `/health`; `api.ingest` CLI |
| `dbutils/` | Shared | Ingest plumbing, auto-sync, visibility helpers |

## Data flow (all pillars)

```text
job → JSON artifact → auto-sync (DSN set) → Postgres → UI / api/
```

UI modules (`*_data.py`) read **only from Postgres** via `*_db_data.py` when a DSN is reachable; disk JSON is used **only** when no DSN is configured (`frontend/db_fallback.py`). Deletes remove both the Postgres row and on-disk artifacts.

## Auth and public/private isolation

Duke OIDC login (`auth/`, see [`auth/README.md`](auth/README.md)). Browsing the public catalog needs no login; starting a run or deleting a result always does (`@require_login`, enforced server-side).

Every pillar has two independent data slices, selected by the public/private toggle at launch time:
- **Public** — shared catalog, visible to everyone.
- **Private** — per-user runs on sibling paths (`frontend/run_paths.py::scoped_dir`, `.private/<owner_user_id>/…`) and Postgres rows (`visibility`, `owner_user_id` in `db/auth_schema.sql`).

Public and private runs of the same model never collide on disk or share a URL (`/scans/<slug>` vs `/scans/<slug>/private`, same pattern for safety/eval/benchmarks).

## Shared helpers (reuse before duplicating)

| Module | Role |
|--------|------|
| `frontend/db_fallback.py` | Postgres-only reads when DSN reachable; disk fallback offline only |
| `frontend/staleness.py` | Per-pillar needs-rerun rules (`dbutils/staleness_spec.py`) |
| `frontend/oss_gateway_hf.py` | HF mirror map for open-weight gateway catalog scan rollup |
| `frontend/delete_db.py` | Shared DB-delete error surfacing for permanent deletes |
| `frontend/launch_registry.py` | In-flight job liveness (`check_inflight_combo`) |
| `frontend/run_paths.py` | Public/private path scoping |
| `frontend/path_safety.py` | Slug validation |
| `frontend/docker_launch.py` | Browser-launched pillar Docker stacks |
| `dbutils/visibility.py` | SQL + artifact visibility checks |
| `dbutils/post_run.py` | Auto-ingest after pillar runs |

## Dependencies

`pyproject.toml` + `uv.lock`. UI/API/tests: `uv sync --group dev` (psycopg is core).

Pillar groups (`scanner`, `safety`, `benchmarks`) conflict — use Docker for pillar jobs; install at most one group on the host if needed.

## CI / deploy

lint (ruff) → unit-tests. On `main`: Buildah → GitLab registry → `deploy` job to VM (manual Play or `DEPLOY_AUTO=true`), target `/home/vcm/security-and-qa-for-ai-models`.

Always start the production UI via `./docker/run.sh` or `python3 main.py` — never bare `docker compose` without the pinned project name `qa-ai-models`.

## Environment (`.env`)

| Variable | Role |
|----------|------|
| `DUKE_GATEWAY_*`, `OPENAI_*` | Gateway for safety/eval/benchmarks |
| `HF_TOKEN` | Scanner gated downloads |
| `POSTGRES_DSN` | Scan, safety, benchmark loaders + UI reads |
| `EFFICACY_DB_DSN` | Eval loader + `/eval-run` (same server usually) |
| `FRONTEND_LAUNCH_MODE=docker` | Browser Start buttons use Docker (default) |
| `AUTO_INGEST=0` | Disable post-run sync |
| `AUTH_ENABLED`, `DUKE_OIDC_*`, `AUTH_ALLOWED_NETIDS` | Duke OIDC login — see `auth/README.md` |

## Hosts

1. **Application VM** (`model-advisor.colab.duke.edu`) — production UI, all pillar Docker jobs, ingest
2. **Duke AI Gateway** — default chat for safety / eval / benchmarks
3. **DCC** — optional open-weight vLLM (`scripts/dcc/`); eval CLI today; safety + benchmarks planned
4. **DGX** — optional dev workstation (not required for production)

Flow diagram: [`docs/architecture.md`](docs/architecture.md#how-a-run-flows)

## Quick run (VM or local)

```bash
uv sync --group dev
cp .env.example .env
./docker/build-pillars.sh
python3 main.py up -d --build
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
```

## Ingest commands

```bash
./scripts/apply-schemas.sh --bootstrap
uv run python -m api.ingest --apply
```

## Test and lint

```bash
uv run ruff check .
uv run python -m unittest discover -s unit_tests -q
```

## Where to read next

| Topic | Doc |
|-------|-----|
| All CLI commands | [`docs/cli.md`](docs/cli.md) |
| REST API | [`api/README.md`](api/README.md) |
| Docker model | [`docs/docker.md`](docs/docker.md) · [`docker/README.md`](docker/README.md) |
| Architecture | [`docs/architecture.md`](docs/architecture.md) |
| Postgres schema | [`docs/data-model.md`](docs/data-model.md) |
| Gateway models | [`docs/gateway-models.md`](docs/gateway-models.md) |
| Frontend routes | [`frontend/README.md`](frontend/README.md) |
