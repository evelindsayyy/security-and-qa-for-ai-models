# API (`api/`)

Flask JSON REST over pipeline results. Blueprints mount under `/api` via
`register_api(app)` in `frontend/create_app` — same process as the dashboard.

Thin handlers over `frontend/*_data.py` (Postgres when configured, else on-disk
JSON). Same payloads as the dashboard; envelope in `api/responses.py`.
`evals.py` is the reference blueprint.

## Mounted

| Method | Path | Data layer |
|--------|------|------------|
| GET | `/api/evals` | `eval_run_data` — `?suite=`, `?model=` |
| GET | `/api/evals/<slug>` | `eval_run_data` |
| GET | `/api/models/<slug>` | `eval_run_data` — rollup across suites |

## In progress

| Method | Path | Data layer |
|--------|------|------------|
| GET | `/api/health` | — |
| GET | `/api/models` | cross-pillar catalog |
| GET | `/api/scans` | `scan_data` |
| GET | `/api/scans/<slug>` | `scan_data` |
| GET | `/api/safety` | `safety_data` |
| GET | `/api/safety/<slug>` | `safety_data` |
| GET | `/api/benchmarks` | `benchmark_data` |
| GET | `/api/benchmarks/<slug>` | `benchmark_data` |
| POST | `/api/scans` | `scan_launch` → `202` + `job_id` |
| POST | `/api/safety` | `safety_launch` → `202` + `job_id` |
| POST | `/api/evals` | `eval_launch` → `202` + `job_id` |
| POST | `/api/benchmarks` | `benchmark_launch` → `202` + `job_id` |

Target flow: [`docs/architecture.md`](../docs/architecture.md).

## Response envelope

```json
{ "ok": true,  "data": <payload>, "error": null }
{ "ok": true,  "data": [...], "error": null, "meta": { "total": N } }
{ "ok": false, "data": null, "error": "message" }
```

## Layout

| File | Role |
|------|------|
| `responses.py` | `ok()` / `err()` |
| `evals.py` | Efficacy reads |
| `scans.py` | Scanning reads |
| `safety.py` | Safety reads |
| `__init__.py` | `register_api(app)` |
| `ingest.py` | CLI orchestrator — `python -m api.ingest` (not a REST route; see [`docs/cli.md`](../docs/cli.md)) |
