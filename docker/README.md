# Application Docker stack

Containerized Flask UI for the application VM. Start it with the launcher, which
auto-detects your user, the Docker socket group, and the repo path:

```bash
./docker/run.sh up --build      # foreground
./docker/run.sh up -d --build   # background
./docker/run.sh down            # stop
```

The repo is bind-mounted at the **same absolute path** inside the container as on
the host, so browser "Start" buttons can launch pillar jobs as sibling containers
through the mounted Docker socket. See [`docs/docker.md`](../docs/docker.md) for
the model and [`docs/cli.md`](../docs/cli.md) for all commands.

Postgres and Redis are external (`POSTGRES_DSN`). CI builds this image on the VCM
(runner tag `codeplus`).
