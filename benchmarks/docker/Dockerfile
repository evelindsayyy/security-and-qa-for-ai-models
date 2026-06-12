FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir \
    openai python-dotenv pyyaml litellm pydantic huggingface-hub \
    pandas numpy requests datasets tqdm bert-score

COPY benchmarks/ /app/benchmarks/

ENV PYTHONPATH=/app
WORKDIR /app/benchmarks

CMD ["python", "run_benchmark.py", "--help"]
