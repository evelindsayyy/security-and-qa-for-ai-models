# Gateway testing (spike)

Gateway connectivity spikes. Production: `evaluator/` (Track B), `safety/` (Track A).

| Script | Purpose |
|--------|---------|
| `duke_gateway.py` | Shared `call_model`, `chain_models` |
| `list_models.py` | `GET /v1/models` — authoritative LiteLLM ids |
| `smoke.py` | One-shot latency/token check |
| `compare_models.py` | Same prompt across N models |

**Env:** `DUKE_AI_GATEWAY_API_KEY` (see repo `.env.example`). Optional: `DUKE_GATEWAY_BASE_URL`.

```bash
export DUKE_AI_GATEWAY_API_KEY=...
cd testing/gateway
uv run python list_models.py
python smoke.py --model "gpt-5.4"
python compare_models.py --models "gpt-5.4" "Llama 3.3"
```

OpenAI SDK variant (display names with spaces): `testing/test_gateway.py`.

Live catalog: `uv run python list_models.py` or frontend `/models` (with gateway env). Reference doc: [`docs/gateway-models.md`](../../docs/gateway-models.md). `Mistral on-site` is deprecated and no longer on the allowlist.
