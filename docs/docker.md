# Docker model

How the images fit together. For commands, see [`cli.md`](cli.md).

## Recommended local path

```bash
./docker/build-pillars.sh    # one-time pillar images
python3 main.py               # containerized UI (default); same as ./docker/run.sh up --build
```

Production on the application VM uses the same scripts. Host Flask (`uv run flask …`) is a development alternative only.

## Two layers

| Layer | Path | Purpose |
|-------|------|---------|
| App | `docker/` | Long-lived Flask UI |
| Job sandboxes | `*/docker/` | One-shot scan / safety / eval / benchmark runs |
| Safety sub-tools | `safety/promptfoo/docker/`, `safety/garak/docker/` | Nested from the safety orchestrator |

Dependencies live in [`pyproject.toml`](../pyproject.toml) + [`uv.lock`](../uv.lock). Core deps include **psycopg**; optional groups: `dev` (pytest, ruff), and **one of** `scanner`, `safety`, or `benchmarks` (mutually exclusive — baked into pillar images instead).

## When Docker is used

| Task | Docker? |
|------|---------|
| Unit tests | No (`uv run …`) |
| **UI (default)** | Yes — `./docker/run.sh` |
| Browser "Start" buttons | Yes (default) |
| HF scanning (untrusted files) | Yes |
| Safety / eval / benchmark jobs from the UI | Yes |

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

GitLab runs lint and unit tests on Duke **shared runners**. On `main`, the
`build-web-image` job uses the dedicated `oit-shared-buildah` runner to build
`docker/Dockerfile` without a Docker socket or DinD, then pushes
`${CI_REGISTRY_IMAGE}/web:${CI_COMMIT_SHORT_SHA}` to the GitLab container
registry. No gateway secrets are required.

**Deploy (manual by default on `main`):** after lint, tests, and `build-web-image`,
the **`deploy`** job SSHs to the application VM, runs `git pull`, logs into the
registry, pulls the tagged web image, and restarts the stack. Click **Play** in
GitLab, or set CI/CD variable **`DEPLOY_AUTO=true`** for automatic deploy. See
[`.gitlab/README.md`](../.gitlab/README.md) for CI/CD variables.

Postgres is external (`POSTGRES_DSN` on OIT host). End-to-end flow diagram: [`architecture.md`](architecture.md#how-a-run-flows).
