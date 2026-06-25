# Public benchmarks (Track B)

Gateway-backed public benchmark pilots — TruthfulQA, IFEval, MMLU, ToMi, and
consistency. The Duke LLM-as-judge eval is separate, in [`../evaluator/`](../evaluator/).

## Layout

```
benchmarks/
  run_benchmark.py      # unified CLI + browser entry (sets env, stable output stem)
  *_test.py             # Jack's original runners (tqa, if, mmlu, tomi, consistency)
  manifest.yaml         # reference catalog (not all implemented)
  results/              # JSON/JSONL output (gitignored)
  db/                   # Postgres schema + loader (see db/README.md)
  docker/               # browser-launched runs
```

`run_benchmark.py` wraps the `*_test.py` scripts so the frontend and Docker launch
any benchmark with one argv shape.

## Run

```bash
# host
uv run python benchmarks/run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"

# docker (matches the browser launch)
export UID=$(id -u) GID=$(id -g)
docker compose --env-file .env \
  -f benchmarks/docker/compose.yml run --rm benchmarks \
  python run_benchmark.py --benchmark ifeval --model "gpt-5-chat"
```

Output lands in `benchmarks/results/` as `<UTC>_<benchmark>_<model>.{json,jsonl}`. When
`POSTGRES_DSN` is set, each run auto-syncs and `/benchmarks` reads from Postgres
(merged with any files not yet loaded). Bulk backfill: `uv run python -m api.ingest bootstrap --apply`.
Credentials come from the repo-root `.env`. Set `FRONTEND_LAUNCH_MODE=host` to skip Docker.

Legacy outputs under `testing/basic_tests/test_results/` are still read as a fallback.

## Custom / self-hosted API

The default models are the Duke gateway catalog, but you can also benchmark via
**Hosted** (HF Inference Providers) or **Custom** (any OpenAI-compatible API you
run — vLLM, Ollama, LiteLLM proxy, or your own server). The browser form is at
`/benchmarks/new`.

### Model input cheat sheet

| Source | When to use | **Model field** | Other fields |
|--------|-------------|-----------------|--------------|
| **Gateway** | Duke catalog models (easiest) | pick from dropdown, e.g. `GPT 4.1 Mini` | — |
| **Hosted** | No GPU / no cluster; HF serves the model | HF repo id: `org/model` or `org/model:provider` | HF token (`hf_…`) with *Inference Providers* permission |
| **Custom** | Your own OpenAI-compatible chat API (local or internal) | Model id your API expects: `my-model`, `gpt-4`, `org/model`, … | Base URL (`http://…/v1`), API key (optional) |

**Format rules:** Hosted uses Hugging Face repo ids (optional `:provider` pin).
Custom accepts any model id string your server's `model` parameter accepts
(letters, digits, `.`, `_`, `-`, `/`, `+`).

The model id is passed to `model_client`, which auto-routes based on the base URL
(Duke gateway, HF router, or self-hosted → `openai/<model-id>`).

### Hosted (no vLLM / DCC setup)

The fastest path — no GPU, no cluster — is **Hugging Face Inference Providers**,
an OpenAI-compatible router. You only need an HF token with the *Inference
Providers* permission ([create one here](https://huggingface.co/settings/tokens)).

CLI:

```bash
export LITELLM_BASE_URL="https://router.huggingface.co/v1"
export TQA_BASE_URL="https://router.huggingface.co/v1"
export OPENAI_API_KEY="hf_your_token"
uv run python benchmarks/run_benchmark.py --benchmark mmlu --model "microsoft/Phi-4-mini-instruct"
```

Browser: pick **Hosted (Hugging Face Inference API)** on `/benchmarks/new`, enter
the repo id and your token. The base URL is fixed to the router server-side.

To force a specific serving provider, pin it on the model id with
`org/model:provider` (e.g. `WeiboAI/VibeThinker-3B:novita`) — both the CLI
`--model` flag and the browser field accept it. Without a pin, the router uses
the providers enabled in your
[account settings](https://huggingface.co/settings/inference-providers) (set to
**auto** to let it pick any available one).

Caveats: the model must be **provider-backed for chat completion** (check the
"Inference Providers" widget on its HF model page; the model has to be served by
a provider you've enabled); there's a metered cost / limited free tier.

**Hosted setup checklist**

1. Pick a model on [HF with Inference Available](https://huggingface.co/models?inference_provider=all&other=conversational) (spark icon on the card).
2. On the model page, open **Inference Providers** — confirm **Chat Completion** is listed (not just Text Generation).
3. If the model is **gated**, accept the license on the model page first.
4. Create a [fine-grained token](https://huggingface.co/settings/tokens) with **Make calls to Inference Providers** (and **Read access to public gated repos** if gated).
5. At [Inference Providers settings](https://huggingface.co/settings/inference-providers), set routing to **Automatic** or enable the specific provider shown on the model page.
6. If auto-routing fails, pin the provider: `org/model:provider` (provider name is on the model page URL/widget, e.g. `:featherless-ai`, `:novita`).

**Example hosted inputs**

| Model field | Notes |
|-------------|--------|
| `meta-llama/Llama-3.1-8B-Instruct` | widely served; accept Meta license first |
| `Qwen/Qwen2.5-7B-Instruct` | ungated, good smoke test |
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0:featherless-ai` | pin Featherless if auto-routing fails |

### Self-hosted API (CLI)

Point the base URL at your server and pass the model id your API expects:

```bash
export LITELLM_BASE_URL="http://localhost:8000/v1"   # or your API's /v1 root
export TQA_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="local-vllm"                   # or your real key; any non-empty value if auth is off
uv run python benchmarks/run_benchmark.py --benchmark mmlu --model "my-model-id"
```

Works with vLLM, Ollama (`/v1`), LiteLLM, or any OpenAI-compatible chat server.

Quick connectivity check before a long run: `curl -s "$LITELLM_BASE_URL/models"`.

> TruthfulQA reads `TQA_BASE_URL` before `LITELLM_BASE_URL`. `run_benchmark.py`
> otherwise defaults it to the Duke gateway, so set `TQA_BASE_URL` too (or use
> the browser flow below, which sets every alias for you).

### Browser

On the **Start a benchmark run** page (`/benchmarks/new`), choose
**Custom (self-hosted API)** and fill in:

- **Model id** — whatever your API expects (e.g. `team-chat-v2`, `Qwen/Qwen3-0.6B`)
- **Base URL** — OpenAI-compatible root, e.g. `http://localhost:8000/v1`
- **API key** — optional; leave blank if your server does not authenticate

The base URL is restricted to internal/private hosts (localhost, private IPs,
or `*.duke.edu` / bare DCC node names) — public addresses are rejected.

Notes:

- **Host mode** (`FRONTEND_LAUNCH_MODE=host`) is the simplest path when the API
  runs on the same machine as the frontend.
- **Docker mode** also works, but the benchmarks container must be able to reach
  the endpoint — prefer a private **IP** (NAT-routable) over a cluster hostname,
  which may not resolve inside the container.

**Custom setup checklist**

1. **Have an API already?** Use its base URL + model id — no vLLM required.
2. **Serving a HF model yourself?** Start vLLM, Ollama, etc., then use that endpoint.
3. **From a laptop to a remote node:** tunnel, e.g. `ssh -N -L 8000:<host>:8000 user@login`, then base URL `http://localhost:8000/v1`.
4. **Model field:** the `model` string your server documents (not necessarily an HF repo id).
5. **API key:** your server's key, or a placeholder if auth is disabled.

**Example custom inputs**

| Model id | Base URL | API key |
|----------|----------|---------|
| `my-finetune-v2` | `http://localhost:8080/v1` | (your key) |
| `Qwen/Qwen3-0.6B` | `http://localhost:8000/v1` (vLLM, tunneled) | `local-vllm` |
| `llama3.1` | `http://localhost:11434/v1` (Ollama) | `ollama` |

## LIST OF BENCHMARKS AND WHAT THEY DO

1. MMLU - mmlu_test.py

MMLU contains 15908 multiple-choice questions spanning 57 different subjects, from complex STEM fields to international law, religion, and even nutrition. The dataset is loaded from HuggingFace. Top human experts can score ~90% on this test.

2. TruthfulQA - tqa_test.py

TruthfulQA measures whether a model avoids repeating common myths and misconceptions. Models are often trained on text that includes these falsehoods, so they can confidently give wrong answers. Examples of questions the model must answer correctly include:

    If you swallow watermelon seeds, a watermelon will grow in your stomach.
    Humans did not actually land on the moon in 1969.
    If you cross paths with a black cat, you will have bad luck.

The program loads questions from TruthfulQA.csv. Sets up multiple-choice question format, choosing 1 answer from "Correct Answers" column and 3 from "Incorrect Answers" column, then randomizes letter placement.

3. IFEval - if_test.py

IFEval measures a model's ability to follow exact instructions according to the prompt. The dataset is loaded from HuggingFace. There are also files instructions_registry.py, instructions_util.py, and instructions.py, which helps set up the official judge.

4. Consistency - consistency_test.py

Consistency measures a model's ability to give the same answer when a prompt is paraphrased. The questions are in consistency_questions.json. The similarity of the answers are measured using BERTscore. BERTScore measures semantic similarity between two pieces of text — it understands that two sentences can mean the same thing even if they use different words.

5. MBPP - mbpp_test.py

MBPP tests a model's ability to generate correct code. It is a set of Python problems built to be solved by entry-level programmers. The questions are loaded from HuggingFace. After querying the model, the generated code is executed and checked under unit tests.

6. QuALITY - quality_test.py

QuALITY tests a model's reading comprehension. The questions are loaded from HuggingFace. It makes the model read a long passage of text, then asks it multiple-choice questions about the passage.

7. ToMi - tomi_test.py

ToMi is a test often used in psychology. It tests one's ability to perceive others' beliefs, even when they might be false. The questions are loaded from tomi_questions.txt. An example question is:

    Jackson entered the hall.
    Chloe entered the hall.
    The boots is in the bathtub.
    Jackson exited the hall.
    Jackson entered the dining_room.
    Chloe moved the boots to the pantry.
    Where does Chloe think that Jackson searches for the boots?

(The correct answer is "bathtub" — because Jackson left the room before Chloe moved the boots, so he still believes they are in the bathtub)