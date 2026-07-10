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

### UI has no styling, or shows an outdated layout

Symptom A — fully unstyled: pages render as plain HTML; browser network tab
shows `404` on `/static/dist/main.js` and no hashed CSS under
`/static/dist/assets/`.

Symptom B — partially/incorrectly styled: hashed assets return `200`, but the
UI still looks outdated (missing layout/design changes you know are on `main`).

**How assets resolve.** `frontend/vite_assets.py` serves the Vite bundle from
the first of these that has a build, and reads the manifest from the same place:

1. `frontend/static/dist` — the *working-tree* build. `docker/run.sh` (and
   `main.py`) rebuild this on the host via `scripts/build-frontend.sh` right
   before starting, so in dev it reflects your latest edits. Gitignored.
2. `/opt/frontend-dist` — the build baked into the image. Production (the VM)
   serves this, because a freshly pulled repo has no working-tree build.

`deploy-remote.sh` removes `frontend/static/dist` on the VM after git sync, so
the VM always serves the fresh image bake (no stale leftover can shadow it).

**Root cause of Symptom B (historical).** Tailwind's `content` scans
`../templates/**/*.html` (see `frontend/assets/tailwind.config.js`). The Docker
`frontend-build` stage must copy `frontend/templates/` into the build context;
otherwise Tailwind can't see class usage in templates and purges every
template-only class (`pillar-toolbar`, `launch-page`, `form-section`, …), baking
an incomplete stylesheet. The Dockerfile now copies templates before
`npm run build`; `unit_tests/test_vite_assets.py` guards against regression.

**Fix:** rebuild so the image bakes a complete, current stylesheet:

```bash
# Dev host:
./docker/run.sh up -d --build --force-recreate
# VM: use the CI deploy (builds a fresh image via buildah, then pulls it).
```

**Verify** the served bundle matches a local build and includes a template-only
class:

```bash
# hash the web container serves:
docker compose --project-name qa-ai-models exec -T web \
  python3 -c "from frontend.vite_assets import vite_entry; print(vite_entry())"
# should match:  (cd frontend/assets && npm run build) and the printed hash
# confirm a template-only class survived purge:
CSS=$(curl -s http://localhost:5000/ | grep -oE '/static/dist/assets/main[^"]*\.css' | head -1)
curl -s "http://localhost:5000$CSS" | grep -c pillar-toolbar   # expect >= 1
```

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
