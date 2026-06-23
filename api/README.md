# API (`api/`)

Flask JSON REST layer over the pipeline's data. Blueprints are mounted under
`/api` by `register_api(app)` (called from `frontend/create_app`), so the API
and the dashboard run in one Flask app today.

## Endpoints (Track B — efficacy)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | liveness + whether the Postgres read-path is reachable |
| GET | `/api/evals` | eval runs (filters: `?suite=`, `?model=`; paged: `?limit=`, `?offset=`) |
| GET | `/api/evals/<slug>` | one run's full detail |
| GET | `/api/models/<slug>` | one model's rollup across suites |

These are thin wrappers over the shared eval data layer
(`frontend/eval_run_data.py`), which dispatches to the Postgres repository
(`evaluator/db/queries.py`) when a DB is configured and falls back to result
files otherwise — so the API returns the **same numbers as the dashboard**,
with or without a database.

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

- `responses.py` — the `ok()` / `err()` envelope helpers + the `@json_errors`
  decorator (shared by all blueprints).
- `evals.py` — the efficacy read blueprint (list + detail + model rollup).
- `health.py` — the liveness blueprint.
- `__init__.py` — `register_api(app)`; Track A adds scans/safety blueprints here.

**Deferred:** `POST` job-launch endpoints (reuse `frontend/*_launch.py` subprocess
path; no Redis/Celery for MVP) and SQLAlchemy/Alembic over the repository — see
[`docs/architecture.md`](../docs/architecture.md).
