# Duke AI Gateway — model catalog

Models on the **Duke AI Gateway** (LiteLLM). Used for **safety**, **efficacy**, and **benchmarks**. **Scanning** uses Hugging Face repo ids, not these strings.

## Authoritative source

| What | Where |
|------|--------|
| Live ids | `GET /v1/models` with your API key ([dashboard.ai.duke.edu](https://dashboard.ai.duke.edu)) |
| Code + cache | [`gateway/catalog.py`](../gateway/catalog.py) — `get_gateway_catalog()` |
| Per-model notes | `ANNOTATIONS` in the same file (shown on frontend `/models`) |
| UI | `/models` in the frontend; **Refresh** forces re-fetch |

Ids are **case- and space-sensitive** — copy exactly (e.g. `GPT 4.1 Mini`, `o4 Mini`).

```bash
uv run python -m gateway          # grouped list with notes
uv run python -m gateway --json   # machine-readable
uv run python -m gateway --ids    # one id per line
```

When OIT adds a model, it appears on the next refresh; unknown ids get a category default note until we add an explicit `ANNOTATIONS` entry.

---

## Categories

| Category | Use in this project |
|----------|---------------------|
| **general_chat** | Safety red-team, Duke efficacy eval, public benchmarks |
| **codex** | Agentic / coding tasks only |
| **research** | Deep research and reasoning — high cost, avoid bulk safety |
| **audio** | Transcription — out of MVP scope unless tasked |
| **embeddings** | Vector search — not chat eval |

---

## Pilot tiers (cost vs capability)

Rough guidance for Track B/A pilots — see live notes on `/models` for each id.

| Tier | Examples | Typical use |
|------|----------|-------------|
| Smoke | `GPT 4.1 Mini`, `gpt-5-nano` | Connectivity, cheap benchmarks |
| Standard | `gpt-5-chat`, `Llama 4 Maverick` | Efficacy + safety default pilots |
| Budget reasoning | `gpt-5-mini` | May need `max_tokens` 2000+ for visible text |
| Premium | `gpt-5.4-pro`, `o3-deep-research` | Spot checks only — high cost |

**Eval cost estimates:** `evaluator/runner.py` → `_COST_PER_M_TOKENS` (keys must match gateway ids exactly).

---

## Deprecated

| Former id | Status |
|-----------|--------|
| `Mistral on-site` | Phased out — not on gateway |

---

## Open-weight models (DCC)

**Default:** safety, eval, and benchmarks use **gateway model ids** from this catalog (HTTPS to LiteLLM).

**Open-weight / self-hosted:** when a model is served on the Duke Compute Cluster
(vLLM on SLURM) instead of the gateway, use the DCC workflow in
[`scripts/dcc/README.md`](../scripts/dcc/README.md).

| Pillar | DCC support |
|--------|-------------|
| **evaluator** | CLI today — `--candidate-endpoint`, `--inference-backend dcc`, `--hf-repo` |
| **safety** | Planned — same endpoint override pattern |
| **benchmarks** | Planned — `inference_backend` in Postgres schema |

Scanning is unchanged: it uses **Hugging Face repo ids**, not gateway ids. Run scans
on HF artifacts before deploying open-weight models on DCC.

---

## On-prem (Azure Foundry)

[`scripts/azure/`](../scripts/azure/README.md) is an example Foundry workflow for a separate
OpenAI-compatible endpoint. Not used in production today.
