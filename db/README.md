# Database scripts (`db/`)

Auth DDL and one-time migration. Pillar schemas remain under `*/db/`.

| File | Purpose |
|------|---------|
| [`auth_schema.sql`](auth_schema.sql) | `users`, `user_run_links`, visibility/fingerprint columns on pillar tables |
| [`migrate_auth_columns.py`](migrate_auth_columns.py) | Backfill fingerprints on existing runs |

```bash
# Apply all schemas (auth first, then pillars)
./scripts/apply-schemas.sh

# Backfill existing Postgres rows
uv run python db/migrate_auth_columns.py          # dry run
uv run python db/migrate_auth_columns.py --apply  # write
```

See [`docs/auth-setup.md`](../docs/auth-setup.md) for the full operator sequence.
