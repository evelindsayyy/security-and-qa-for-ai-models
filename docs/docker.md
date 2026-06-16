# Docker model

How the images fit together. For commands, see [`cli.md`](cli.md).

## Two layers

| Layer | Path | Purpose |
|-------|------|---------|
| App | `docker/` | Long-lived Flask UI for the application VM |
| Job sandboxes | `*/docker/` | One-shot scan / safety / eval / benchmark runs |
| Safety sub-tools | `safety/promptfoo/docker/`, `safety/garak/docker/` | Nested from the safety orchestrator |

Dependencies live in [`pyproject.toml`](../pyproject.toml) + [`uv.lock`](../uv.lock) — no root `requirements.txt`. Optional groups: `dev` (pytest, ruff), `db` (psycopg), `safety`, `benchmarks`.

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

GitLab runs on the Code+ shared VM (runner tag **`codeplus`**): lint → unit tests
→ Docker build → manual deploy on `main`. No gateway secrets in CI. See
[`.gitlab-ci.yml`](../.gitlab-ci.yml) and [`.gitlab/README.md`](../.gitlab/README.md).

Postgres and Redis are external (`POSTGRES_DSN`). The full VM stack (Redis,
Celery, `api/`) is W5 — see [`architecture.md`](architecture.md).
