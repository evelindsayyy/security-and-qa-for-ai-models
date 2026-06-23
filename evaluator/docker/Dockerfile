FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --group db

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

COPY dbutils/ /app/dbutils/
COPY evaluator/ /app/evaluator/

WORKDIR /app/evaluator

CMD ["python", "runner.py", "--help"]
