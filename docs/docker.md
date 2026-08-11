# Docker model

How images and compose stacks fit together. **Commands:** [`cli.md`](cli.md#web-ui-containerized) · [`docker/README.md`](../docker/README.md).

## Recommended paths

| Environment | Start |
|-------------|-------|
| Local / DGX | `./docker/run.sh up -d --build` · after pulls/code changes: `./docker/run.sh restart` |
| Application VM | CI **deploy** (preferred) or `./docker/run.sh restart` with production `.env` |

Host Flask (`python3 main.py --host`) is for UI-only iteration; pillar jobs still
use Docker unless `FRONTEND_LAUNCH_MODE=host`.

## Layers

| Layer | Path | Purpose |
|-------|------|---------|
| App | `docker/` | Long-lived Flask UI (multi-stage: Node + Python) |
| Job sandboxes | `*/docker/` | One-shot scan / safety / eval / benchmark runs |
| Safety sub-tools | `safety/promptfoo/docker/`, `safety/garak/docker/` | Nested from the safety orchestrator |

Dependencies: [`pyproject.toml`](../pyproject.toml) + [`uv.lock`](../uv.lock). Core
includes **psycopg**; optional groups `dev`, and **one of** `scanner` / `safety` /
`benchmarks` (mutually exclusive on the host — baked into pillar images instead).

## When Docker is used

| Task | Docker? |
|------|---------|
| Unit tests | No (`uv run …`) |
| UI (default) | Yes — `./docker/run.sh` |
| Browser Start buttons | Yes (default) |
| HF scanning | Yes |
| Safety / eval / benchmark from UI | Yes |

Set `FRONTEND_LAUNCH_MODE=host` to run pillar jobs as host Python instead.

## How the UI launches jobs

The app container uses the **host** Docker daemon via `/var/run/docker.sock` and
starts pillar containers as siblings. `docker/run.sh` auto-detects:

| Value | Why |
|-------|-----|
| `HOST_UID` / `HOST_GID` | Run as the host user; outputs not root-owned |
| `DOCKER_GID` | Access to the Docker socket |
| `HOST_REPO` | Same absolute repo path in and out of the container |

All stacks share `COMPOSE_PROJECT_NAME=qa-ai-models`.

## Frontend assets

| Source | When | Location |
|--------|------|----------|
| Working-tree build | Dev: `run.sh` runs `scripts/build-frontend.sh` before start | `frontend/static/dist/` (gitignored) |
| Image bake | CI / `docker build`; VM when no working-tree build | `/opt/frontend-dist` in the container |

The Dockerfile frontend-build stage runs `npm ci && npm run build` and copies
`frontend/templates/` into the build context (Tailwind scans `../templates/**/*.html`).
`frontend/vite_assets.py` resolves manifest + file serving from one directory:
working-tree first, image bake as fallback.

## CI and deploy

GitHub Actions pipeline on hosted runners:

1. **lint** (ruff) → **unit-tests** → **frontend-build** (`npm ci`, `npm run build`, vitest)
2. On **`main`**: **build-web-image** (Buildx) → `ghcr.io/evelindsayyy/security-and-qa-for-ai-models:${GITHUB_SHA}`
3. **deploy** — manual workflow dispatch on `main` by default (`DEPLOY_AUTO=true` for automatic)

The deploy job SSHs to the application VM, runs `git pull`, pulls `WEB_IMAGE`,
and recreates `web` (+ `caddy` when `CADDY_DOMAIN` is set). See
[`.github/README.md`](../.github/README.md).

Postgres is external. End-to-end flow: [`architecture.md`](architecture.md#how-a-run-flows).

## Production HTTPS (Caddy)

On the application VM, set in `.env`:

```env
CADDY_DOMAIN=model-advisor.colab.duke.edu
TRUST_PROXY=1
CADDY_EMAIL=your-netid@duke.edu
```

`docker/run.sh` and `deploy-remote.sh` add [`compose.caddy.yml`](../docker/compose.caddy.yml):

- **Caddy** — ports 80/443, Duke Locksmith ACME (`locksmith.oit.duke.edu`)
- **web** — internal only (not published on `:5000` when Caddy is active)
- Flask trusts `X-Forwarded-Proto` when `TRUST_PROXY=1`

Do not enable Caddy locally; the overlay targets the production domain only.

Troubleshooting: [`docker/README.md`](../docker/README.md).
