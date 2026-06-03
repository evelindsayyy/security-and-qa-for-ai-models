# Duke AI Gateway — model catalog (reference)

Models available through the **Duke AI Gateway** (LiteLLM / Azure-backed). Used for **safety** (Track A) and **efficacy** (Track B). Not used for **scanning** — scanning uses Hugging Face repo IDs on DGX.

Confirm exact **LiteLLM `model=` strings** with OIT

| LiteLLM `model=` (spike) | Alias | Notes |
|----------------------------|-------|-------|
| `gpt-5.4` | duke-gpt54 | TruthfulQA, LiteLLM scripts |
| `Llama 3.3` | duke-llama33 | |
| `Mistral on-site` | duke-mistral | **Deprecated** — do not add new runs |
| `GPT 4.1 Mini` | — | OpenAI SDK (`testing/test_gateway.py`) |

---

## Deployment types

| Type | Scanning (HF artifacts) | Safety / efficacy (gateway) |
|------|-------------------------|-----------------------------|
| **Cloud gateway** (closed weights via API) | N/A until model is hosted as HF on-prem | Primary now (~10 models) |
| **On-prem OSS** (future) | Required before deploy | Same gateway or direct endpoint TBD |

---

## General chat models (cloud)

| Gateway model (confirm ID) | Provider | Input | Output | Notes |
|----------------------------|----------|-------|--------|-------|
| GPT-5.4 | OpenAI | $2.50 | $15.00 | Flagship* |
| GPT-5.3-chat, GPT-5.2, GPT-5.2-chat | OpenAI | $1.75 | $14.00 | |
| GPT-5.1, GPT-5.1-chat | OpenAI | $1.25 | $10.00 | |
| GPT-5, GPT-5-chat | OpenAI | $1.25 | $10.00 | |
| GPT-5-mini | OpenAI | $0.25 | $2.00 | Good pilot tier |
| GPT-5-nano | OpenAI | $0.05 | $0.40 | Cheapest OpenAI chat |
| GPT-4.1 | OpenAI | $2.00 | $8.00 | |
| GPT-4.1-mini | OpenAI | $0.40 | $1.60 | **Default smoke test** (see test_gateway.py) |
| GPT-4.1-nano | OpenAI | $0.10 | $0.40 | |
| GPT-OSS 120B | OpenAI | $0.15 | $0.60 | Open-weight style via cloud |
| Llama 3.3 | Meta | $0.71 | $0.71 | |
| Llama 4 Maverick | Meta | $0.35 | $1.41 | |
| Llama 4 Scout | Meta | $0.20 | $0.78 | Low-cost Llama pilot |

---

## Specialty models (cloud)

Use only when a task explicitly requires them (Track B may use; Track A safety usually uses **general chat** models).

| Model | Notes |
|-------|--------|
| GPT-5.4-pro | Gateway only; very high cost — avoid bulk red-team |
| GPT-5.x-codex family | Coding / agentic evals |
| GPT-4o-transcribe* | Audio — out of scope summer unless tasked |
| o3, o4-mini, *-deep-research | Research-style — optional efficacy |
| text-embedding-3-* | Embeddings — not chat safety |
| whisper-1 | Audio — out of scope |

---

## Scanning test models (HF on DGX — not gateway)

Separate catalog for **artifact scanning** on DGX (`scanner/models/`, `scanner/output/`):

| HF `MODEL_ID` | Role |
|---------------|------|
| distilbert-base-uncased | Default regression |
| gpt2 | Calibration baseline |
| facebook/opt-125m | Org/model path |
| bert-base-uncased | Tier 1 |
| sentence-transformers/all-MiniLM-L6-v2 | Fast regression |

On-prem pilot (week 7+): map gateway **Llama 4** / **GPT-OSS** to HF repos when OIT confirms hosting.

---


## Open decisions 

- Canonical list of ~10 production gateway models for nutrition label v1
- Exact LiteLLM model string for each row in this doc
- Which Llama/OpenAI models are “open” via cloud only vs future on-prem HF
- Mistral deprecation date
