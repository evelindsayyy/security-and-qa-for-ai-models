# API (`api/`)

Flask REST service (week 5+): enqueue scans, safety, evals to Celery; serve GET results from Postgres.

- Design: [`docs/architecture.md`](../docs/architecture.md)
- UI: [`frontend/`](../frontend/) (same application-factory pattern)

```bash
uv sync
uv run flask --app frontend:create_app run --debug   # UI spike until api/ is wired
```
