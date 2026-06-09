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
| `/` | Hub — scan/eval/safety counts, gateway model list |
| `/safety` | Merged safety labels from `safety/output/*/merged_safety_result.json` |
| `/safety/<slug>` | One model safety detail (findings, suites, deployment context) |
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
| `scan_data.py` | Load `scanner/output/*/scan_result.json`; detail view uses findings tables, tool panels, and filters (like eval/benchmarks) |
| `eval_run_data.py` | Load and summarize `evaluator/results/*.jsonl` |
| `safety_data.py` | Load `safety/output/*/merged_safety_result.json`; detail uses findings tables, suite panels, filters (like scans) |
| `routes.py` | Flask routes (lazy imports for eval/scanner loaders) |
| `templates/` | Jinja HTML |
| `static/style.css` | Shared table + tier badge styles |

## Related docs

- [`docs/architecture.md`](../docs/architecture.md) — target API and UI
- [`docs/data-model.md`](../docs/data-model.md) — Postgres shapes
- [`scanner/README.md`](../scanner/README.md) — artifact scanning
- [`evaluator/README.md`](../evaluator/README.md) — efficacy runner
- [`safety/README.md`](../safety/README.md) — promptfoo + garak red-team pipeline

**Safety (gateway env required):**

```bash
# see safety/README.md — promptfoo eval, garak scan, then merge
PYTHONPATH=. uv run python -m safety.merge \
  --promptfoo safety/promptfoo/output/safety_result.json \
  --promptfoo safety/promptfoo/output/redteam_safety_result.json \
  --garak safety/garak/output/safety_result.json \
  -o safety/output/gpt-4.1-mini/merged_safety_result.json
```
