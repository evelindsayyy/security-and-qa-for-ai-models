# Duke AI Gateway — model catalog (reference)

Models available through the **Duke AI Gateway** (LiteLLM / Azure-backed). Used for **safety** (Track A) and **efficacy** (Track B). Not used for **scanning** — scanning uses Hugging Face repo IDs on DGX.

**Authoritative ids:** `GET https://litellm.oit.duke.edu/v1/models` with your LiteLLM API key ([dashboard.ai.duke.edu](https://dashboard.ai.duke.edu)). Strings are **case- and space-sensitive** — copy exactly.

Refresh from the repo:

```bash
uv run python testing/gateway/list_models.py
```

The draft frontend `/models` page loads the same live list when `DUKE_GATEWAY_URL` + `DUKE_GATEWAY_KEY` are set in repo-root `.env`.

---

## Deployment types

| Type | Scanning (HF artifacts) | Safety / efficacy (gateway) |
|------|-------------------------|-----------------------------|
| **Cloud gateway** (closed weights via API) | N/A until model is hosted as HF on-prem | Primary now |
| **On-prem OSS** (future) | Required before deploy | Same gateway or direct endpoint TBD |

---

## General chat (safety + efficacy)

Pilot / smoke models are marked in the **Notes** column. Use these for Track B `runner.py` and Track A safety unless a task needs a specialty model.

| LiteLLM `model=` (live) | Provider | Notes |
|-------------------------|----------|-------|
| `GPT 4.1` | OpenAI | Display name uses spaces + capitals |
| `GPT 4.1 Mini` | OpenAI | **Default smoke test** (`testing/test_gateway.py`) |
| `GPT 4.1 Nano` | OpenAI | Low-cost OpenAI chat |
| `gpt-5` | OpenAI | Base GPT-5 |
| `gpt-5-chat` | OpenAI | **IT support eval candidate (default)** |
| `gpt-5-mini` | OpenAI | Good pilot tier — low cost |
| `gpt-5-nano` | OpenAI | Cheapest OpenAI chat — smoke tier |
| `gpt-5.1` | OpenAI | |
| `gpt-5.1-chat` | OpenAI | |
| `gpt-5.2` | OpenAI | |
| `gpt-5.2-chat` | OpenAI | |
| `gpt-5.3-chat` | OpenAI | |
| `gpt-5.4` | OpenAI | TruthfulQA pilot (`duke-gpt54`) |
| `gpt-5.4-mini` | OpenAI | |
| `gpt-5.4-nano` | OpenAI | |
| `gpt-5.5` | OpenAI | |
| `gpt-oss-120b` | OpenAI | Open-weight style via cloud (id is lowercase) |
| `Llama 3.3` | Meta | TruthfulQA pilot (`duke-llama33`) |
| `Llama 4 Maverick` | Meta | **IT support eval judge (default)** |
| `Llama 4 Scout` | Meta | Low-cost Llama pilot |

**Pricing (evaluator cost estimates):** see `evaluator/runner.py` `_COST_PER_M_TOKENS` — keys must match the ids above exactly.

---

## Codex / agentic coding

Use only when a task explicitly requires coding or agentic evals.

| LiteLLM `model=` | Notes |
|------------------|-------|
| `gpt-5-codex` | |
| `gpt-5.1-codex` | |
| `gpt-5.1-codex-max` | |
| `gpt-5.1-codex-mini` | |
| `gpt-5.2-codex` | |
| `gpt-5.3-codex` | |

---

## Research / reasoning

| LiteLLM `model=` | Notes |
|------------------|-------|
| `o3-deep-research` | High cost — avoid bulk red-team |
| `o4 Mini` | Note capital M in `Mini` |
| `o4-mini-deep-research` | |
| `gpt-5.4-pro` | Gateway only; very high cost |

---

## Audio / transcription

Out of scope for summer MVP unless explicitly tasked.

| LiteLLM `model=` | Notes |
|------------------|-------|
| `gpt-4o-transcribe` | |
| `gpt-4o-transcribe-diarize` | |
| `whisper-1` | |

---

## Embeddings

Not used for chat safety or IT-support efficacy.

| LiteLLM `model=` | Notes |
|------------------|-------|
| `text-embedding-3-small` | |
| `text-embedding-3-large` | |

---

## Deprecated (do not use)

| Former id | Status |
|-----------|--------|
| `Mistral on-site` | **Phased out** — not returned by `GET /v1/models`; remove from new runs |


---

