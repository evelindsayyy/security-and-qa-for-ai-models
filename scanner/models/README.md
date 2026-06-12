# HF weights (gitignored, ephemeral)

Populated during `python -m scanner scan <repo_id>` (or the browser **Start scan** flow).
**Deleted automatically** once `output/<slug>/scan_result.json` is written, unless
`SCAN_KEEP_WEIGHTS=1`.

Only JSON under `scanner/output/` is kept long-term — that is what the UI and
Postgres ingest read. A rescan re-downloads from Hugging Face Hub.

**Keep weights for debugging:**

```bash
SCAN_KEEP_WEIGHTS=1 docker compose -f scanner/docker/compose.yml run --rm scanner \
  python -m scanner scan gpt2
```

**Supply-chain calibration (local fixture):** `scan-test--supply-chain-demo/` — rescan with
`SCAN_KEEP_WEIGHTS=1` if you need the snapshot to stay between runs; otherwise each
`python -m scanner scan scan-test/supply-chain-demo` fetches fresh weights.

Gateway model IDs (cloud APIs) live in [`gateway/`](../../gateway/README.md) /
[`docs/gateway-models.md`](../../docs/gateway-models.md) — not here.
