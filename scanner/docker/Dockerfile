FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# TruffleHog (Go binary) for secret scanning.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
       | sh -s -- -b /usr/local/bin \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --group scanner

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV HF_HOME=/app/scanner/models/.cache/huggingface

COPY scanner/ /app/scanner/

CMD ["bash"]
