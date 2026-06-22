FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --group db --group benchmarks

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app

COPY dbutils/ /app/dbutils/
COPY benchmarks/ /app/benchmarks/

WORKDIR /app/benchmarks

CMD ["python", "run_benchmark.py", "--help"]
