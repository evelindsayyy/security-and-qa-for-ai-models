# API (`api/`)

Flask JSON REST over pipeline results. Blueprints mount under `/api` via
`register_api(app)` in `frontend/create_app` — same process as the dashboard.

Thin handlers over `frontend/*_data.py` (Postgres when DSN configured, else on-disk
JSON). Same payloads as the dashboard; envelope in `api/responses.py`.
`evals.py` is the reference blueprint.

## Mounted

| Method | Path | Data layer |
|--------|------|------------|
| GET | `/api/health` | liveness + whether the Postgres read-path is reachable |
| GET | `/api/evals` | `eval_run_data` — filters `?suite=`, `?model=`; paged `?limit=`, `?offset=` |
| GET | `/api/evals/<slug>` | `eval_run_data` |
| GET | `/api/models/<slug>` | `eval_run_data` — rollup across suites |

## In progress

| Method | Path | Data layer |
|--------|------|------------|
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

### Pagination (`/api/evals`)

Filters apply first, then the result is paged. `meta.total` is the full
filtered count (so a client knows how many pages exist); `data` is the current
page.

- `?limit=` page size — default `50`, capped at `200`.
- `?offset=` rows to skip — default `0`.
- Non-integer or negative values → `400`.

```json
{ "ok": true, "data": [ ... ], "error": null,
  "meta": { "total": 16, "limit": 2, "offset": 0 } }
```

`/api/health` reports `db_available: false` when reads are being served from
result files (the documented fallback, not an error).

## Response envelope

Every response is the same shape, including internal failures (a data-layer
exception is logged server-side and returned as a JSON `500`, never Flask's
HTML error page):

```json
{ "ok": true,  "data": <payload>, "error": null }                    // success
{ "ok": true,  "data": [...], "error": null, "meta": {"total": N} }  // list
{ "ok": false, "data": null, "error": "message" }                    // 4xx / 5xx
```

## Layout

| File | Role |
|------|------|
| `responses.py` | `ok()` / `err()` envelope helpers + the `@json_errors` decorator |
| `evals.py` | Efficacy reads (list + detail + model rollup; paging) |
| `health.py` | Liveness blueprint |
| `ingest.py` | CLI orchestrator — `python -m api.ingest` (not a REST route; see [`docs/cli.md`](../docs/cli.md)) |
| `__init__.py` | `register_api(app)` |
| `scans.py` | Scanning reads *(planned)* |
| `safety.py` | Safety reads *(planned)* |
