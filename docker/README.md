# Application Docker stack

Containerized Flask UI (default for local dev and the application VM). Scripts
auto-detect your user, the Docker socket group, and the repo path.

**One-time** — build pillar job images (required before browser **Start** buttons work):

```bash
./docker/build-pillars.sh
```

**Run the UI** — builds the web image on first `up --build`:

```bash
python3 main.py up --build      # foreground (same as ./docker/run.sh)
python3 main.py up -d --build   # background
python3 main.py down            # stop
python3 main.py logs -f web     # logs
```

The repo is bind-mounted at the **same absolute path** inside the container as on
the host, so browser "Start" buttons can launch pillar jobs as sibling containers
through the mounted Docker socket. See [`docs/docker.md`](../docs/docker.md) for
the model and [`docs/cli.md`](../docs/cli.md) for all commands.

Postgres is external (`POSTGRES_DSN` on OIT host).

| Script | Role |
|--------|------|
| `host-env.sh` | Shared `HOST_*` and pillar `UID`/`GID` (bash `UID` is readonly) |
| `build-pillars.sh` | One-time pillar image builds |
| `deploy-remote.sh` | VM deploy (git pull + registry pull + compose up) |
| `compose.deploy.yml` | Use `WEB_IMAGE` from CI instead of local build |
| `compose.caddy.yml` | Production HTTPS overlay (auto-included when `CADDY_DOMAIN` set) |
| `Caddyfile` | Caddy TLS + reverse proxy config |

Production HTTPS: [`docs/docker.md`](../docs/docker.md#production-https-caddy).

## Container HOME layout

The web service sets `HOME` to `<repo>/.docker-home/<HOST_UID>`. Docker CLI config
(`config.json`, buildx state) is stored there per host UID. This prevents GitLab
deploy (`DEPLOY_USER`) and interactive VM users from colliding on a shared
`.docker-home` and breaking `docker compose` inside the container.

## Troubleshooting

### "Docker is required for browser-launched … runs"

Symptom: Start buttons fail after a CI deploy; restarting via `python3 main.py`
from an interactive session fixes it.

**Likely cause:** the container runs as `HOST_UID` from whoever last ran `up`, but
Docker CLI config in `.docker-home` was created by a different UID (mode `0700`).
`docker compose version` then fails with `permission denied` on `config.json`.

**Diagnose:**

```bash
docker compose --project-name qa-ai-models -f docker/compose.yml ps
docker compose --project-name qa-ai-models logs web --tail 80 | grep -i compose
ls -la .docker-home/*/.docker/config.json 2>/dev/null
```

**Fix:** redeploy via `./docker/run.sh up -d --force-recreate` or GitLab deploy
so `entrypoint.sh` creates a per-UID HOME. Do not share one `.docker-home` across
users.

### UI has no styling (unstyled HTML, `/static/dist/main.js` 404)

Symptom: pages render as plain HTML; browser network tab shows `404` on
`/static/dist/main.js` and no hashed CSS under `/static/dist/assets/`.

**Cause:** `frontend/static/dist/` is gitignored. A bind-mounted repo after
`git pull` has no Vite build. `vite_assets.py` falls back to `dist/main.js`,
which does not exist (production bundles are hashed, e.g. `main-BE6YOoG2.js`).

**Fix:** restart the web container so `entrypoint.sh` seeds dist from the image
bake at `/opt/frontend-dist`:

```bash
./docker/run.sh up -d --force-recreate
```

Or copy manually inside the running container:

```bash
docker compose --project-name qa-ai-models exec web \
  cp -a /opt/frontend-dist/. "${HOST_REPO}/frontend/static/dist/"
```

**Prevent:** deploy pulls a CI-built `WEB_IMAGE` that already contains
`/opt/frontend-dist`; entrypoint copies it on start when the host manifest is
missing.

### Port 5000 already in use

```bash
ss -ltnp | grep ':5000'
docker ps --format '{{.Names}}\t{{.Ports}}'
```

Kill stray containers not in project `qa-ai-models`. **Never run `main.py --host`
on the shared VM** — it binds port 5000 outside Docker and blocks the production
container.

### Deploy fails health wait

`deploy-remote.sh` uses `--wait --wait-timeout 90`. If CI deploy fails:

```bash
docker compose --project-name qa-ai-models -f docker/compose.yml logs web
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool
```

### Always use the pinned project name

`docker/compose.yml` sets `name: qa-ai-models`. Ad-hoc `docker compose` without
`--project-name qa-ai-models` can create stray projects that compete for port 5000.
