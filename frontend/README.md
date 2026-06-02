# Frontend (`frontend/`)

Nutrition label UI (Flask). Merged from Grace's `flaskr` mockup (model list + efficacy table).

```bash
uv sync
uv run flask --app frontend:create_app run --debug
# or: python main.py
```

| Route | Purpose |
|-------|---------|
| `/` | Home — gateway model names from `catalog.py` |
| `/dashboard` | Mockup table (`mockup_data.py`, v0.0.1) |
| `/models` | Gateway catalog (docs-aligned) |
| `/hello` | Smoke test |

Week 5+: poll `api/`. `instance/` at repo root is gitignored (Flask local DB). Tasks: [`.gitlab/README.md`](../.gitlab/README.md).
