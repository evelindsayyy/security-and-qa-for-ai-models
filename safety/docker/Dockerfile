FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends docker.io bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml /app/
RUN pip install --no-cache-dir python-dotenv pyyaml openai pydantic litellm

COPY safety/ /app/safety/
COPY gateway/ /app/gateway/

ENV PYTHONPATH=/app

CMD ["bash", "safety/run_safety.sh", "--help"]
