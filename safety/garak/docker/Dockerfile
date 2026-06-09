FROM python:3.11-slim

ARG GARAK_VERSION=

RUN pip install --no-cache-dir "garak${GARAK_VERSION:+==${GARAK_VERSION}}" && \
    mkdir -p /app/safety/garak/output/.garak-home /app/safety/garak/output/.garak-cache

WORKDIR /app/safety/garak

ENV XDG_DATA_HOME=/app/safety/garak/output/.garak-data
ENV XDG_CACHE_HOME=/app/safety/garak/output/.garak-cache
ENV XDG_CONFIG_HOME=/app/safety/garak/output/.garak-config

CMD ["bash"]
