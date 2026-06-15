# Gateway catalog (`gateway/`)

Single source for **which models exist on the Duke AI Gateway** (`GET /v1/models`, 5‑min cache).

Used by: frontend `/models`, safety/eval/benchmark launch dropdowns, `python -m gateway` CLI.

## Model notes

Concise descriptions live in **`catalog.py` → `ANNOTATIONS`** (one string per exact LiteLLM id). The `/models` page shows them in the Notes column. New gateway ids get a **category default** until we add an explicit entry.

Edit `ANNOTATIONS` when OIT adds or renames models — then refresh the UI or wait for cache expiry.

## CLI

```bash
uv run python -m gateway          # grouped by category + notes
uv run python -m gateway --json   # JSON array
uv run python -m gateway --ids    # one id per line
```

## Python API

```python
from gateway import get_gateway_catalog, list_model_ids, eligible_models

get_gateway_catalog(force_refresh=True)  # UI refresh button
eligible_models()                        # chat-capable ids for launch forms
```

## Env

Repo-root `.env`: `DUKE_GATEWAY_URL` + `DUKE_GATEWAY_KEY` (or `OPENAI_BASE_URL` / `OPENAI_API_KEY`).

More context: [`docs/gateway-models.md`](../docs/gateway-models.md).
