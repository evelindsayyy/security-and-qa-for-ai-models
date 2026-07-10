FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg bash \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin bash \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
# Venv lives at /opt/venv (not /app/.venv) so the repo-root volume mount
# at runtime doesn't shadow the image-baked dependencies.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-install-project --group safety

ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app

COPY dbutils/ /app/dbutils/
COPY safety/ /app/safety/
COPY gateway/ /app/gateway/

CMD ["python", "-m", "safety.run", "--help"]
