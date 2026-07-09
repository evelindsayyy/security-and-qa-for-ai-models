# frontend/docker — dashboard images

Two artifacts, two jobs. The **dev compose** is for iterating locally; the
**Dockerfile** is the reproducible image CI builds and a deploy ships.

| File | Use | Source | Server |
|---|---|---|---|
| `compose.yml` | local dev | bind-mounted (hot reload) | `flask run --debug` |
| `Dockerfile` | CI build / deploy | `COPY`ed, baked from `uv.lock` | `flask run` (no debug) |

## Dev

```bash
# from the repo root (one root .env holds the secrets)
docker compose --env-file .env -f frontend/docker/compose.yml up --build
# open http://localhost:3000
```

## Production image

```bash
docker build -f frontend/docker/Dockerfile -t qa-frontend .
docker run --rm -p 3000:5001 --env-file .env qa-frontend
```

Wire into CI as the `build` job: `docker compose -f frontend/docker/compose.yml build`
(or `docker build -f frontend/docker/Dockerfile`). Keep `deploy` manual until
there's a real host — see the CI plan.

## The launch-button caveat (open team decision)

The dashboard launches per-pillar runs (eval/scan/safety/benchmark) by shelling
out to `docker compose … run` ([`../docker_launch.py`](../docker_launch.py)).
**Neither image here contains a Docker daemon**, so from inside a container that
path can't work. Three ways forward:

1. **View-only deploy (recommended for now).** Ship the dashboard to *read*
   results (files + Postgres) — the comparison table, per-model page, and detail
   pages all work with zero Docker. Trigger runs from the CLI.
2. **Docker-out-of-Docker.** Add the Docker CLI + mount `/var/run/docker.sock`.
   Launch buttons work, but the socket is root-on-host and compose paths get
   tricky against the host daemon.
3. **Host-mode in-container** (`FRONTEND_LAUNCH_MODE=host`, set in both files).
   Runs execute in-process: evaluator/benchmark work (deps are in the image),
   but safety/scanner need their own toolchains and won't launch from here.

This is a cross-pillar decision (it affects everyone's launch buttons), so it
belongs with the team/mentor, not this directory.

## Notes

- `.dockerignore` (repo root) is an allowlist; `frontend/**` and `uv.lock` were
  added so the production `COPY` actually includes the app and the lockfile.
- The venv is built at `/opt/venv` (not `/app/.venv`) so a bind mount can't
  shadow it with the host's macOS venv.
- Base is `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` — matches the project's
  `requires-python >=3.13` and ships uv, unlike the 3.11 pillar images.
