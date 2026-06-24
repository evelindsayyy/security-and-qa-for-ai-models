#!/usr/bin/env bash
set -euo pipefail
exec uv run python -m scripts.dcc.vllm wait "$@"
