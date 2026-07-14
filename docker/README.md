# Application Docker stack

Containerized Flask UI for local dev and the application VM. Scripts auto-detect
`HOST_UID`, `HOST_GID`, `DOCKER_GID`, and `HOST_REPO` — do not set these in `.env`.

## Quick start

**One-time** — pillar images (required for browser **Start** buttons):

```bash
./docker/build-pillars.sh
```

**Run the UI** — [`docs/cli.md`](../docs/cli.md#web-ui-containerized)

```bash
./docker/run.sh up -d --build
./docker/run.sh restart      # after git pull
./docker/run.sh down
./docker/run.sh logs -f web
# Same: python3 main.py … or uv run python main.py …
```

Use project name **`qa-ai-models`** (set in `compose.yml`).

The repo is bind-mounted at the **same absolute path** inside and outside the
container so pillar jobs launched via the Docker socket resolve bind mounts on the
host. Postgres is external (`POSTGRES_DSN`).

## Production (application VM)

Set in `.env`:

```env
CADDY_DOMAIN=model-advisor.colab.duke.edu
TRUST_PROXY=1
```

When `CADDY_DOMAIN` is set, `run.sh` and `deploy-remote.sh` include
`compose.caddy.yml`: Caddy terminates TLS on 443 and proxies to `web`. Without
it, only `web` listens on `APP_PORT` (default 5000) — suitable for dev and SSH
tunnels, not public HTTPS.

Preferred update path: GitLab CI **deploy** job (pulls registry image, recreates
`web` + `caddy`). Manual fallback: `git pull && ./docker/run.sh up -d --build --force-recreate`.

Detail: [`docs/docker.md`](../docs/docker.md).

## Files

| Path | Role |
|------|------|
| `Dockerfile` | Multi-stage web image (Node frontend build + Python runtime) |
| `run.sh` | Local start; builds host frontend assets; includes Caddy when configured |
| `host-env.sh` | Shared `HOST_*` and pillar `UID`/`GID` |
| `entrypoint.sh` | Per-UID Docker CLI `HOME` under `.docker-home/<uid>` |
| `compose.yml` | Base `web` service |
| `compose.caddy.yml` | Caddy overlay (80/443) |
| `compose.deploy.yml` | CI registry image (`WEB_IMAGE`) |
| `deploy-remote.sh` | VM deploy: git sync, registry pull, compose up |
| `Caddyfile` | TLS + reverse proxy (Duke Locksmith ACME) |
| `build-pillars.sh` | One-time pillar image builds |

## Frontend assets in the image

The web image bakes Vite output at `/opt/frontend-dist`. The Docker frontend-build
stage copies `frontend/assets/` **and** `frontend/templates/` so Tailwind can scan
template class usage. `docker/run.sh` also runs `scripts/build-frontend.sh` on the
host before start (working-tree build in `frontend/static/dist/`).

`frontend/vite_assets.py` serves the working-tree build when present, else the image
bake. `deploy-remote.sh` removes `frontend/static/dist` on the VM so production
always uses the CI-built image bundle.

## Container HOME

`HOME` is `<repo>/.docker-home/<HOST_UID>`. Deploy ensures `.docker-home` is
group-writable so CI deploy users and interactive VM users do not collide on Docker
CLI config.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Start buttons fail after deploy | `.docker-home` UID mismatch | `./docker/run.sh up -d --force-recreate` or redeploy |
| Unstyled / 404 on `/static/dist/…` | Missing frontend build | Dev: `./docker/run.sh up -d --build`. VM: CI deploy with `frontend-build` + `build-web-image` |
| `https://…` unreachable, `localhost:5000` works | `CADDY_DOMAIN` unset or Caddy not running | Set `CADDY_DOMAIN` + `TRUST_PROXY=1`; confirm `qa-ai-models-caddy-1` is up |
| Port 5000 in use | Stray process or wrong compose project | `ss -ltnp \| grep :5000`; use `--project-name qa-ai-models` |
| Deploy health wait timeout | Web failed to start | `docker compose --project-name qa-ai-models logs web`; `curl -s http://127.0.0.1:5000/api/health` |

Do not run `python3 main.py --host` on the shared VM — it binds port 5000 outside
Docker and blocks the production container.
