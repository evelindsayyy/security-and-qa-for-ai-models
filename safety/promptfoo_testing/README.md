# Promptfoo Testing

This directory is for Promptfoo safety and red-team experiments against Duke AI Gateway models.

Use this space for Promptfoo configs, Docker setup, notes, and reproducible command examples. Generated red-team cases, reports, logs, and Promptfoo local state should go in `output/`, which is ignored by Git except for its README.

Suggested layout:

```text
safety/promptfoo_testing/
  README.md
  promptfooconfig.yaml
  promptfooconfig.redteam.yaml
  docker/
    Dockerfile
    compose.yml
    .env.example
  output/
    README.md
```

Do not commit API keys, `.env` files, or large generated Promptfoo outputs. Keep checked-in files small enough for teammates to inspect and rerun.

## Docker workflow

Run these commands from the repository root.

Create a local Docker environment file:

```bash
cp safety/promptfoo_testing/docker/.env.example safety/promptfoo_testing/docker/.env
```

On Linux or DGX, set the container user to your current user so generated output files are editable in VS Code:

```bash
sed -i "s/^UID=.*/UID=$(id -u)/" safety/promptfoo_testing/docker/.env
sed -i "s/^GID=.*/GID=$(id -g)/" safety/promptfoo_testing/docker/.env
```

Edit `safety/promptfoo_testing/docker/.env` and set `OPENAI_API_KEY` to a Duke AI Gateway key.

Build the Promptfoo image:

```bash
docker compose --env-file safety/promptfoo_testing/docker/.env \
  -f safety/promptfoo_testing/docker/compose.yml build
```

Run the red-team scan:

```bash
docker compose --env-file safety/promptfoo_testing/docker/.env \
  -f safety/promptfoo_testing/docker/compose.yml run --rm promptfoo \
  promptfoo redteam run -c promptfooconfig.redteam.yaml \
  -o output/redteam.yaml \
  --delay 500 \
  --max-concurrency 1 \
  --force
```

View the red-team report:

```bash
docker compose --env-file safety/promptfoo_testing/docker/.env \
  -f safety/promptfoo_testing/docker/compose.yml run --rm --service-ports promptfoo \
  promptfoo redteam report -p 15500
```

Open `http://localhost:15500` while the report command is running. If port `15500` is already in use, use another published port:

```bash
PROMPTFOO_REPORT_PORT=15501 docker compose --env-file safety/promptfoo_testing/docker/.env \
  -f safety/promptfoo_testing/docker/compose.yml run --rm --service-ports promptfoo \
  promptfoo redteam report -p 15500
```

Then open `http://localhost:15501`.

The Dockerfile only installs Promptfoo and exposes the report port. Red-team run and report commands are runtime actions, so they belong in this README or in Docker Compose commands rather than in the Dockerfile.
