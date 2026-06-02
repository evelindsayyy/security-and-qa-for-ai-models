FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir garak pandas requests

RUN npm install -g promptfoo

CMD ["bash"]
