FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    openai python-dotenv pyyaml litellm pydantic huggingface-hub

COPY evaluator/ /app/evaluator/

ENV PYTHONPATH=/app
WORKDIR /app/evaluator

CMD ["python", "runner.py", "--help"]
