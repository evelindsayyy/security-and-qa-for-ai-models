FROM node:22-slim

ARG PROMPTFOO_VERSION=latest

RUN apt-get update && \
    apt-get install -y --no-install-recommends bash ca-certificates python3 && \
    npm install -g "promptfoo@${PROMPTFOO_VERSION}" && \
    npm cache clean --force && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app/safety/promptfoo_testing

ENV PROMPTFOO_CONFIG_DIR=/app/safety/promptfoo_testing/output/.promptfoo
ENV PROMPTFOO_LOG_DIR=/app/safety/promptfoo_testing/output/logs

EXPOSE 15500

CMD ["bash"]
