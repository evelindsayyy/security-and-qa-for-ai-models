# Application VM image: Python deps + Docker CLI + Node for frontend asset builds.
# Application code is bind-mounted at runtime (HOST_REPO), not baked in.
# Build via: ./docker/run.sh up --build

FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend/assets
COPY frontend/assets/package.json frontend/assets/package-lock.json* ./
RUN npm ci
COPY frontend/assets/ ./
# Tailwind's content scan includes ../templates/**/*.html (see tailwind.config.js).
# The templates must be present in the build context or Tailwind purges every
# class used only in templates (pillar-toolbar, launch-page, form-section, …),
# baking an incomplete stylesheet and an unstyled production UI.
COPY frontend/templates/ /build/frontend/templates/
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg bash nodejs npm \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
         docker-ce-cli docker-compose-plugin docker-buildx-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/deps
COPY pyproject.toml uv.lock ./
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/opt/venv/bin:$PATH"

# Seed built frontend assets (bind-mounted repo may overwrite; entrypoint rebuilds if missing).
COPY --from=frontend-build /build/frontend/static/dist /opt/frontend-dist

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["flask", "--app", "frontend:create_app", "run", "--host", "0.0.0.0", "--port", "5000"]
