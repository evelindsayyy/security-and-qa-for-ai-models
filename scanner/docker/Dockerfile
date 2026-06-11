FROM python:3.11-slim

WORKDIR /app

# TruffleHog (Go binary) for secret scanning — pinned install script version.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
       | sh -s -- -b /usr/local/bin \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scanner/ /app/scanner/

ENV PYTHONPATH=/app
ENV HF_HOME=/app/scanner/models/.cache/huggingface

CMD ["bash"]
