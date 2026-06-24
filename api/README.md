# API (`api/`)

Flask JSON REST over pipeline results. Blueprints mount under `/api` via
`register_api(app)` in `frontend/create_app` — same process as the dashboard.

Thin handlers over `frontend/*_data.py` (reads) and `frontend/*_launch.py`
(writes). Same payloads as the dashboard; envelope in `api/responses.py`.
Bulk Postgres ingest is CLI-only: `python -m api.ingest` (see [`docs/cli.md`](../docs/cli.md)).

## Mounted routes

| Method | Path | Data / launch layer |
|--------|------|---------------------|
| GET | `/api/health` | liveness + per-pillar Postgres availability |
| GET | `/api/scans` | `scan_data` — paged `?limit=`, `?offset=` |
| GET | `/api/scans/<slug>` | `scan_data` |
| GET | `/api/scans/<slug>/status` | `scan_launch.get_status` |
| POST | `/api/scans` | `scan_launch` → `202` + `job_id` |
| GET | `/api/safety` | `safety_data` — optional `?profile=`; paged |
| GET | `/api/safety/<slug>/<profile>` | `safety_data` |
| GET | `/api/safety/<slug>/<profile>/status` | `safety_launch.get_status` |
| POST | `/api/safety` | `safety_launch` → `202` + `job_id` |
| GET | `/api/evals` | `eval_run_data` — filters `?suite=`, `?model=`; paged |
| GET | `/api/evals/<slug>` | `eval_run_data` |
| GET | `/api/evals/<slug>/status` | `eval_launch.get_status` |
| POST | `/api/evals` | `eval_launch` → `202` + `job_id` |
| GET | `/api/models/<slug>` | `eval_run_data` — rollup across suites |
| GET | `/api/benchmarks` | `benchmark_data` — paged |
| GET | `/api/benchmarks/<slug>` | `benchmark_data` |
| GET | `/api/benchmarks/<slug>/status` | `benchmark_launch.get_status` |
| POST | `/api/benchmarks` | `benchmark_launch` → `202` + `job_id` |

Target flow: [`docs/architecture.md`](../docs/architecture.md).

### POST job bodies (JSON)

**Scans** — `POST /api/scans`

```json
{ "hf_repo": "gpt2", "skip_modelscan": false, "skip_fickling": false }
```

**Safety** — `POST /api/safety`

```json
{
  "model": "GPT 4.1 Mini",
  "redteam_profile": "base",
  "run_policy": true,
  "run_redteam": true,
  "run_garak": false,
  "garak_probes": "encoding,promptinject"
}
```

**Evals** — `POST /api/evals`

```json
{
  "candidate": "gpt-5-chat",
  "judge": "Llama 4 Maverick",
  "suite": "it_support_v1",
  "max_tokens": 2000
}
```

**Benchmarks** — `POST /api/benchmarks`

```json
{ "benchmark": "truthfulqa", "model": "GPT 4.1 Mini" }
```

**202 response** (all pillars):

```json
{
  "ok": true,
  "data": {
    "job_id": "gpt2",
    "status": "running",
    "status_url": "/api/scans/gpt2/status",
    "already_running": false
  },
  "error": null
}
```

Poll `status_url` until `status` is `complete` or `failed`, then GET the detail route.

### Troubleshooting

- **503 on POST** — output directory not writable (often root-owned from an old Docker run). **DGX (no sudo):** `docker run --rm -v "$PWD/scanner/output:/out" -u root busybox chown -R "$(id -u):$(id -g)" /out`. **With sudo:** `chown -R "$USER" scanner/output`. Export `UID`/`GID` before compose so new runs write as your user.
- **`db_available: false`** — DSN missing, Postgres unreachable, or schemas not applied. Reads fall back to disk JSON. Run `GET /api/health` after setting `POSTGRES_DSN` and applying schemas.

### Pagination (list endpoints)

Filters apply first, then the result is paged. `meta.total` is the full
filtered count; `data` is the current page.

- `?limit=` page size — default `50`, capped at `200`.
- `?offset=` rows to skip — default `0`.
- Non-integer or negative values → `400`.

### Health

```json
{
  "ok": true,
  "data": {
    "status": "ok",
    "db_available": true,
    "pillars": { "scan": true, "safety": true, "eval": true, "benchmark": false }
  },
  "error": null
}
```

`db_available: false` means reads use on-disk JSON until Postgres is configured and reachable.

## Response envelope

Every response is the same shape:

```json
{ "ok": true,  "data": <payload>, "error": null }
{ "ok": true,  "data": [...], "error": null, "meta": {"total": N, "limit": 50, "offset": 0} }
{ "ok": false, "data": null, "error": "message" }
```

## Layout

| File | Role |
|------|------|
| `responses.py` | `ok()` / `err()` envelope + `@json_errors` |
| `paging.py` | shared `?limit` / `?offset` parsing |
| `launch_helpers.py` | JSON body parsing + `202 Accepted` helper |
| `health.py` | Liveness blueprint |
| `scans.py` | Scan read/write |
| `safety.py` | Safety read/write |
| `evals.py` | Efficacy read/write + model rollup |
| `benchmarks.py` | Benchmark read/write |
| `ingest.py` | CLI orchestrator — `python -m api.ingest` (not a REST route) |
| `__init__.py` | `register_api(app)` |

## Planned

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/models` | cross-pillar catalog |
