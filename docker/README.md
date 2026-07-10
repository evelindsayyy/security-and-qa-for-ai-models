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
UI still looks outdated (missing layout/design changes you know are on
`main`).

**Cause:** `frontend/static/dist/` is gitignored, so a bind-mounted repo has no
Vite build after `git pull`. `frontend/vite_assets.py` resolves both the
manifest and the served files from `/opt/frontend-dist` — the copy baked into
the image at build time from current source — so the UI is correctly styled
even when the bind-mounted `frontend/static/dist/` is empty (Symptom A) or
contains a stale build seeded by an older image (Symptom B). `entrypoint.sh`
additionally resyncs the bind mount from the image on every container start
(clean replace, not merge) purely so on-disk state matches what's served; this
is not required for correct rendering.

**Fix:** rebuild and recreate the web container so the image bakes fresh
assets from current source and the entrypoint resyncs the bind mount:

```bash
./docker/run.sh up -d --build --force-recreate
```

If styling still looks wrong after that, confirm the image actually contains a
fresh bake (compare the hash in the page's `<script>`/`<link>` tags against a
local `npm run build` in `frontend/assets/`), and check the container logs for
`Synced frontend static dist from image bake` — its absence with a
`warning: cannot write` means the bind mount isn't writable by the container
UID (harmless for styling, but worth fixing per the `.docker-home` section
above).

**Verify:**

```bash
docker compose --project-name qa-ai-models exec -T web \
  python3 -c "from frontend.vite_assets import vite_entry; print(vite_entry())"
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:5000/static/$(docker compose --project-name qa-ai-models exec -T web python3 -c 'from frontend.vite_assets import vite_entry; print(vite_entry())' | tr -d '\r')"
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
