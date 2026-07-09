# Production image for the efficacy dashboard (frontend/).
#
# Reproducible by design: deps are baked from uv.lock (--frozen), source is
# COPYed (no bind mount), and the debug server is OFF. Build/run from repo root:
#
#   docker build -f frontend/docker/Dockerfile -t qa-frontend .
#   docker run --rm -p 3000:5001 --env-file .env qa-frontend   # -> localhost:3000
#
# Secrets come from runtime env (CI/CD variables or --env-file), never baked in.
# This image VIEWS results (result files + Postgres). Browser-launched runs need
# a Docker strategy (socket mount or host execution) — see README.md.
#
# Requires .dockerignore to allow `frontend/**` and `uv.lock` in the context
# (added for this image; the older pillar images used pip + requirements.txt).

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# 1) Dependency layer — cached unless pyproject.toml / uv.lock change.
#    --no-install-project: this flat app repo has no [build-system]; code is
#    imported from /app, not installed as a package. --group db pulls in psycopg
#    for the dashboard's Postgres read path (it still falls back to files).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --group db

# 2) App layer — source changes don't bust the dependency cache above.
COPY . .

# In a container without Docker, host mode is the only way "Start run" could
# spawn anything; leave it explicit. Flip/remove per the deploy decision.
ENV FRONTEND_LAUNCH_MODE=host

EXPOSE 5001

# Flask's built-in server is acceptable for an internal demo deploy. For a
# hardened deployment, add gunicorn to deps and use:
#   gunicorn -b 0.0.0.0:5001 "frontend:create_app()"
CMD ["flask", "--app", "frontend:create_app", "run", "--host", "0.0.0.0", "--port", "5001"]
