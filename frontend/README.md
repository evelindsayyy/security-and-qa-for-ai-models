# Frontend (`frontend/`)

Temporary, read-only progress viewer for the Duke model nutrition label. It loads JSON from local pipeline output directories so users can see real scanning and efficacy results without Postgres or the API.

The production UI (week 6) will read from the database via `api/` and support interactive runs. This draft only reflects whatever is already on disk under `scanner/output/` and `evaluator/results/` (both gitignored — each developer sees their own fresh data after running the tools locally).

## Run locally

```bash
uv sync
uv run flask --app frontend:create_app run --debug
# or: python main.py
```

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Hub — scan/eval counts, safety placeholder, gateway model list |
| `/scans` | All HF `scan_result.json` rows from `scanner/output/` |
| `/scans/<slug>` | One scan detail (findings, coverage, tool_results) |
| `/eval-run` | Aggregated efficacy runs from `evaluator/results/*.jsonl` |
| `/models` | Live gateway catalog (`GET /v1/models`) + static HF scan list |

## Populate data (read-only UI — run tools separately)

**Scanning (DGX or host with scanner deps):**

```bash
cd scanner/docker   # or host with requirements installed
python -m scanner scan gpt2
# → scanner/output/gpt2/scan_result.json
```

**Efficacy (gateway env required):**

```bash
# .env at repo root: DUKE_GATEWAY_URL, DUKE_GATEWAY_KEY (see evaluator/README.md)
cd evaluator
uv run python runner.py \
  --candidate-model "gpt-5-chat" \
  --judge-model "Llama 4 Maverick"
# → evaluator/results/<timestamp>_it_support_v1_gpt-5-chat.jsonl
```

Refresh the browser after new files appear; no restart needed.

## Layout

| Module | Role |
|--------|------|
| `gateway_catalog.py` | Live gateway ids via `GET /v1/models` (5 min cache) |
| `hf_scan_catalog.py` | HF scan rows from `scanner/output/*/scan_result.json` |
| `scan_data.py` | Load and summarize `scanner/output/*/scan_result.json` |
| `eval_run_data.py` | Load and summarize `evaluator/results/*.jsonl` |
| `routes.py` | Flask routes (lazy imports for eval/scanner loaders) |
| `templates/` | Jinja HTML |
| `static/style.css` | Shared table + tier badge styles |

## Related docs

- [`docs/architecture.md`](../docs/architecture.md) — target API and UI
- [`docs/data-model.md`](../docs/data-model.md) — Postgres shapes
- [`scanner/README.md`](../scanner/README.md) — artifact scanning
- [`evaluator/README.md`](../evaluator/README.md) — efficacy runner
