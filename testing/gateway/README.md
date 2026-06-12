# Gateway testing (spike)

Gateway connectivity spikes. Production: `evaluator/` (Track B), `safety/` (Track A).

| Script | Purpose |
|--------|---------|
| `duke_gateway.py` | Shared `call_model`, `chain_models` |
| `smoke.py` | One-shot latency/token check |
| `compare_models.py` | Same prompt across N models |

**Env:** `DUKE_GATEWAY_KEY` (and `DUKE_GATEWAY_URL`) from the repo-root `.env`.

```bash
cd testing/gateway
python smoke.py --model "gpt-5.4"
python compare_models.py --models "gpt-5.4" "Llama 3.3"
```

OpenAI SDK variant (display names with spaces): `testing/test_gateway.py`.

**Live catalog** moved to the shared [`gateway/`](../../gateway/README.md) package —
`uv run python -m gateway` (or the frontend `/models` page). Reference doc:
[`docs/gateway-models.md`](../../docs/gateway-models.md). `Mistral on-site` is deprecated.
