FROM node:22-slim

ARG PROMPTFOO_VERSION=latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends bash ca-certificates python3 python3-yaml && \
    npm install -g "promptfoo@${PROMPTFOO_VERSION}" && \
    npm cache clean --force && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app/safety/promptfoo

ENV PROMPTFOO_CONFIG_DIR=/app/safety/promptfoo/output/.promptfoo
ENV PROMPTFOO_LOG_DIR=/app/safety/promptfoo/output/logs

EXPOSE 15500

CMD ["bash"]
