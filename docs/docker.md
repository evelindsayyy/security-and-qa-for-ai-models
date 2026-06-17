# Docker model

How the images fit together. For commands, see [`cli.md`](cli.md).

## Two layers

| Layer | Path | Purpose |
|-------|------|---------|
| App | `docker/` | Long-lived Flask UI for the application VM |
| Job sandboxes | `*/docker/` | One-shot scan / safety / eval / benchmark runs |
| Safety sub-tools | `safety/promptfoo/docker/`, `safety/garak/docker/` | Nested from the safety orchestrator |

Dependencies live in [`pyproject.toml`](../pyproject.toml) + [`uv.lock`](../uv.lock). Optional groups: `dev` (pytest, ruff), `db` (psycopg), `scanner`, `safety`, `benchmarks`.

## When Docker is used

| Task | Docker? |
|------|---------|
| Unit tests, local UI dev | No (`uv run …`) |
| Browser "Start" buttons | Yes (default) |
| HF scanning (untrusted files) | Yes |
| Safety / eval / benchmark jobs from the UI | Yes |
| Production UI on the VM | Yes — `docker/run.sh` |

Set `FRONTEND_LAUNCH_MODE=host` to run pillar jobs as host Python instead of Docker.

## How the containerized UI launches jobs

The app container talks to the **host** Docker daemon through the mounted socket
(`/var/run/docker.sock`) and starts pillar containers as siblings — not nested.
For that to work, [`docker/run.sh`](../docker/run.sh) auto-detects three
host-specific values so they never live in `.env`:

| Value | Why |
|-------|-----|
| `HOST_UID` / `HOST_GID` | Run as you, so outputs are not root-owned |
| `DOCKER_GID` | Group of the Docker socket, so the container can reach the daemon |
| `HOST_REPO` | The repo is mounted at the **same absolute path** inside and out, so pillar bind mounts (resolved by the host daemon) point at real files |

All stacks share `COMPOSE_PROJECT_NAME=qa-ai-models`, so an image built on the
host or in CI is reused when the UI launches a job.

## CI

GitLab runs on Duke **shared runners** (`docker+machine`): lint → unit tests only.
No Docker builds in CI (runners lack socket/DinD). No gateway secrets. See
[`.gitlab-ci.yml`](../.gitlab-ci.yml).

Postgres is external (`POSTGRES_DSN` on OIT host). W5 adds `api/` REST on the application VM — see [`architecture.md`](architecture.md).
