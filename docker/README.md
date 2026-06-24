# Application Docker stack

Containerized Flask UI (default for local dev and the application VM). Scripts
auto-detect your user, the Docker socket group, and the repo path.

**One-time** — build pillar job images (required before browser **Start** buttons work):

```bash
./docker/build-pillars.sh
```

**Run the UI** — builds the web image on first `up --build`:

```bash
python main.py up --build      # foreground (same as ./docker/run.sh)
python main.py up -d --build   # background
python main.py down            # stop
python main.py logs -f web     # logs
```

The repo is bind-mounted at the **same absolute path** inside the container as on
the host, so browser "Start" buttons can launch pillar jobs as sibling containers
through the mounted Docker socket. See [`docs/docker.md`](../docs/docker.md) for
the model and [`docs/cli.md`](../docs/cli.md) for all commands.

Postgres is external (`POSTGRES_DSN` on OIT host).
