FROM python:3.11-slim

ARG GARAK_VERSION=

# Pin with GARAK_VERSION=0.10.0 in docker/.env for reproducibility; empty = latest.
RUN pip install --no-cache-dir "garak${GARAK_VERSION:+==${GARAK_VERSION}}" && \
    mkdir -p /app/safety/garak_testing/output/.garak-home /app/safety/garak_testing/output/.garak-cache

WORKDIR /app/safety/garak_testing

# Keep garak cache/state on the bind-mounted output volume (gitignored).
ENV XDG_DATA_HOME=/app/safety/garak_testing/output/.garak-data
ENV XDG_CACHE_HOME=/app/safety/garak_testing/output/.garak-cache
ENV XDG_CONFIG_HOME=/app/safety/garak_testing/output/.garak-config

CMD ["bash"]
