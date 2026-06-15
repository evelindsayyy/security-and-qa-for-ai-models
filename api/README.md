# API (`api/`)

Flask REST + Celery (planned). Until then: [`frontend/`](../frontend/) for UI; [`evaluator/db/`](../evaluator/db/README.md) for the live efficacy Postgres path.

**Persistence:** SQL schema files + psycopg loaders (same pattern as `evaluator/db/`). Ingest validates JSON with existing Pydantic/dataclass schemas, then upserts via parameterized SQL. See [`docs/architecture.md`](../docs/architecture.md) and [`docs/data-model.md`](../docs/data-model.md).

[`docs/architecture.md`](../docs/architecture.md) · [`.gitlab/README.md`](../.gitlab/README.md).
