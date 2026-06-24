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

## Custom Hugging Face / vLLM models

The default models are the Duke gateway catalog, but you can also benchmark any
Hugging Face model via **Hosted** (HF Inference Providers) or **Custom** (your own
vLLM / DCC server). The browser form is at `/benchmarks/new`.

### Model input cheat sheet

| Source | When to use | **Model field** | Other fields |
|--------|-------------|-----------------|--------------|
| **Gateway** | Duke catalog models (easiest) | pick from dropdown, e.g. `GPT 4.1 Mini` | — |
| **Hosted** | No GPU / no cluster; HF serves the model | HF repo id: `org/model` or `org/model:provider` | HF token (`hf_…`) with *Inference Providers* permission |
| **Custom** | Any HF repo you self-host (vLLM on DCC, tunnel, etc.) | HF repo id: `org/model` | Base URL (`http://…:8000/v1`), API key (optional) |

**Format rules (all sources):** use the id from the model’s Hugging Face page
(e.g. `Qwen/Qwen3-0.6B`, `meta-llama/Llama-3.1-8B-Instruct`). Letters, digits,
`/`, `.`, `_`, `-` only. For hosted only, you may append `:provider` to pin a
provider (e.g. `TinyLlama/TinyLlama-1.1B-Chat-v1.0:featherless-ai`).

The model id is passed to `model_client`, which auto-routes based on the base URL
(Duke gateway, HF router, or local vLLM → `openai/<repo-id>`).

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

### Self-hosted vLLM (CLI)

Point the base URL at your server and pass the repo id as `--model`:

```bash
export LITELLM_BASE_URL="http://<node>:8000/v1"   # e.g. from scripts/dcc/wait_vllm.sh
export OPENAI_API_KEY="local-vllm"                 # any non-empty value for unauthenticated vLLM
uv run python benchmarks/run_benchmark.py --benchmark truthfulqa --model "Qwen/Qwen3-0.6B"
```

Quick connectivity check before a long run: `curl -s "$LITELLM_BASE_URL/models"`.

> TruthfulQA reads `TQA_BASE_URL` before `LITELLM_BASE_URL`. `run_benchmark.py`
> otherwise defaults it to the Duke gateway, so set `TQA_BASE_URL` too (or use
> the browser flow below, which sets every alias for you).

### Browser

On the **Start a benchmark run** page (`/benchmarks/new`), choose
**Custom model (self-hosted vLLM)** and fill in:

- **Hugging Face model** — the repo id, e.g. `Qwen/Qwen3-0.6B`
- **Base URL** — your endpoint, e.g. `http://dcc-plusds-gpu-02:8000/v1`
- **API key** — optional; defaults to `local-vllm`

The base URL is restricted to internal/private hosts (localhost, private IPs,
or `*.duke.edu` / bare DCC node names) — public addresses are rejected.

Notes:

- **Host mode** (`FRONTEND_LAUNCH_MODE=host`) is the simplest path for DCC vLLM,
  since the run inherits the endpoint directly.
- **Docker mode** also works, but the benchmarks container must be able to reach
  the endpoint — prefer a private **IP** (NAT-routable) over a cluster hostname,
  which may not resolve inside the container.

**Custom (vLLM) setup checklist**

1. Start vLLM on DCC: `MODEL="org/model" scripts/dcc/start_vllm.sh` then `scripts/dcc/wait_vllm.sh` (see [`scripts/dcc/README.md`](../scripts/dcc/README.md)).
2. Note the node hostname and port (usually `:8000/v1`) from the session file or logs.
3. **From your laptop:** the compute node is not reachable directly — use an SSH tunnel, e.g. `ssh -N -L 8000:<node>:8000 user@dcc-login`, then Base URL `http://localhost:8000/v1`.
4. **Model field:** same HF repo id you passed to vLLM (e.g. `Qwen/Qwen3-0.6B`).
5. **API key:** `local-vllm` or leave blank (vLLM does not authenticate by default).

**Example custom inputs**

| Model | Base URL | API key |
|-------|----------|---------|
| `Qwen/Qwen3-0.6B` | `http://localhost:8000/v1` (tunneled) | `local-vllm` |
| `WeiboAI/VibeThinker-3B` | `http://dcc-plusds-gpu-02:8000/v1` (from login node / host-mode frontend) | `local-vllm` |

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