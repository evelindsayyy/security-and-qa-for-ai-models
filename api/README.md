# API (`api/`)

Flask JSON REST layer over the pipeline's data. Blueprints are mounted under
`/api` by `register_api(app)` (called from `frontend/create_app`), so the API
and the dashboard run in one Flask app today.

## Endpoints (Track B — efficacy)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/evals` | all eval runs (filters: `?suite=`, `?model=`) |
| GET | `/api/evals/<slug>` | one run's full detail |
| GET | `/api/models/<slug>` | one model's rollup across suites |

These are thin wrappers over the shared eval data layer
(`frontend/eval_run_data.py`), which dispatches to the Postgres repository
(`evaluator/db/queries.py`) when a DB is configured and falls back to result
files otherwise — so the API returns the **same numbers as the dashboard**,
with or without a database.

## Response envelope

```json
{ "ok": true,  "data": <payload>, "error": null }          // success
{ "ok": true,  "data": [...], "error": null, "meta": {"total": N} }  // list
{ "ok": false, "data": null, "error": "message" }          // 4xx
```

## Layout

- `responses.py` — the `ok()` / `err()` envelope helpers (shared by all blueprints).
- `evals.py` — the efficacy read blueprint.
- `__init__.py` — `register_api(app)`; Track A adds scans/safety blueprints here.

**Deferred:** `POST` job-launch endpoints (reuse `frontend/*_launch.py` subprocess
path; no Redis/Celery for MVP) and SQLAlchemy/Alembic over the repository — see
[`docs/architecture.md`](../docs/architecture.md).
