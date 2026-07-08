# VM runbook — repopulate safety + scanner (after code deploy)

Run on the **application VM** (`model-advisor.colab.duke.edu`) from the repo root after pulling the delete-integrity + staleness changes.

## Prerequisites

```bash
cd /home/vcm/security-and-qa-for-ai-models   # or your deploy path
git pull
./docker/build-pillars.sh
./docker/run.sh up -d --build
curl -s http://127.0.0.1:5000/api/health | python3 -m json.tool   # db_available: true
```

## 1. Inspect current safety runs (Postgres)

```bash
uv run python - <<'PY'
import os, psycopg
from dbutils import load_repo_env, resolve_dsn
load_repo_env()
dsn = resolve_dsn("POSTGRES_DSN", "DATABASE_URL")
with psycopg.connect(dsn) as conn, conn.cursor() as cur:
    cur.execute("""
        SELECT gateway_model_id, redteam_profile, completed_at,
               missing_suites, status,
               (SELECT count(DISTINCT probe_id) FROM public.safety_findings f
                WHERE f.run_id = s.id AND f.probe_suite = 'garak_subset_v1') AS garak_probes
        FROM public.safety_runs s
        WHERE visibility = 'public'
        ORDER BY gateway_model_id, redteam_profile, completed_at DESC
    """)
    for row in cur.fetchall():
        print(row)
PY
```

**Stale signals** (also shown in UI badges after deploy):
- `completed_at` before **2026-07-01**
- `missing_suites` non-empty
- `garak_probes` &lt; **26**
- `status` not `complete`

## 2. List gateway models needing base-profile safety runs

```bash
uv run python -m gateway --ids > /tmp/gateway_ids.txt
# Compare against Postgres list above; queue models with no base row or stale row.
```

## 3. Safety runs — 5 models at a time (base profile)

Wait for each batch to finish (UI detail log or `safety/output/<slug>/base/run.log`) before starting the next batch.

**Batch example** (replace models with your queue):

```bash
BATCH=(
  "GPT 4.1 Mini"
  "GPT 4.1"
  "gpt-5-chat"
  "Llama 3.3"
  "Llama 4 Maverick"
)

for model in "${BATCH[@]}"; do
  echo "=== Starting safety: $model (base) ==="
  docker compose --project-name qa-ai-models --env-file .env \
    -f safety/docker/compose.yml run --rm safety \
    python -m safety.run "$model" --profile base
done
```

Or via UI: `/safety/new` → select model → base profile → Policy + Red-team + Garak → Start. Use list-page **Needs rerun** badge and primary **Rerun** button for stale rows.

After each batch:

```bash
uv run python -m api.ingest --apply --pillar safety
```

## 4. Open-source gateway scans (non-gated HF repos)

Mapped in [`frontend/oss_gateway_hf.py`](../frontend/oss_gateway_hf.py). Verify each repo is reachable **without** `HF_TOKEN`:

```bash
for repo in \
  "NousResearch/Meta-Llama-3.3-70B-Instruct" \
  "unsloth/Llama-4-Maverick-17B-128E-Instruct" \
  "unsloth/Llama-4-Scout-17B-16E-Instruct"
do
  echo "=== $repo ==="
  docker compose --project-name qa-ai-models --env-file .env \
    -f scanner/docker/compose.yml run --rm scanner \
    python -m scanner scan "$repo" || echo "FAILED: $repo"
done
```

If a 70B repo is too large for disk, switch `GATEWAY_HF_SCAN_REPOS["Llama 3.3"]` in `oss_gateway_hf.py` to a quantized mirror and rescan.

**Stale scan signals** (UI badge):
- `0 files scanned`
- `scanned_at` before **2026-07-01**
- incomplete status

Rerun stale scans with the same `scanner scan` command or UI **Rerun** on `/scans`.

After scans:

```bash
uv run python -m api.ingest --apply --pillar scan
```

Scans of mapped HF repos appear on `/models` under the matching gateway row (e.g. **Llama 3.3**) via `oss_gateway_hf` rollup linking.

## 5. Verify deletes and reads

1. Delete a test run from the UI (list **Delete**).
2. Confirm it disappears from the list and detail URL returns 404.
3. Confirm `scanner/output/<slug>/` or `safety/output/<slug>/` is removed on disk.
4. Confirm Postgres row is gone:

```bash
uv run python -m api.ingest --dry-run --pillar scan   # should not resurrect deleted slug
```

## 6. Full ingest refresh (optional)

```bash
uv run python -m api.ingest bootstrap --apply
```
