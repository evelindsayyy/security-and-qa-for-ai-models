# Public benchmarks

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
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env \
  -f benchmarks/docker/compose.yml run --rm benchmarks \
  python run_benchmark.py --benchmark ifeval --model "gpt-5-chat"
```

Output lands in `benchmarks/results/` as `<UTC>_<benchmark>_<model>.{json,jsonl}`. When
`POSTGRES_DSN` is set, each run auto-syncs and `/benchmarks` reads from Postgres
(merged with any files not yet loaded). Bulk backfill: `uv run python -m api.ingest bootstrap --apply`.
Credentials come from the repo-root `.env`. Set `FRONTEND_LAUNCH_MODE=host` to skip Docker.

Legacy outputs under `testing/basic_tests/test_results/` are still read as a fallback.

Full CLI patterns: [`docs/cli.md`](../docs/cli.md).

## Model input

Form: `/benchmarks/new`. Cheat sheet below.

**Scope**

- **UI** (`/benchmarks/new`): Gateway (dropdown), Hosted (HF Inference Providers), Custom (OpenAI-compatible URL).
- **REST** (`POST /api/benchmarks`): **gateway models only** today — see [`api/README.md`](../api/README.md).

### Cheat sheet

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

### Hosted (HF Inference Providers)

OpenAI-compatible router — no local GPU. Token needs *Inference Providers* permission ([create one](https://huggingface.co/settings/tokens)).

```bash
export LITELLM_BASE_URL="https://router.huggingface.co/v1"
export TQA_BASE_URL="https://router.huggingface.co/v1"
export OPENAI_API_KEY="hf_your_token"
uv run python benchmarks/run_benchmark.py --benchmark mmlu --model "microsoft/Phi-4-mini-instruct"
```

On `/benchmarks/new`, pick **Hosted**; base URL is fixed server-side. Pin a provider with `org/model:provider` if auto-routing fails.

**Hosted setup (short checklist)**

1. Pick a model with [Inference Available](https://huggingface.co/models?inference_provider=all&other=conversational) on HF.
2. Confirm at least one provider on the model page; accept license if gated.
3. Fine-grained HF token with **Make calls to Inference Providers**.
4. Enable providers at [Inference Providers settings](https://huggingface.co/settings/inference-providers) (Automatic or a named provider).
5. Smoke-test: playground accepts `messages` (chat), not prompt-only completion.

**Example hosted inputs:** `meta-llama/Llama-3.1-8B-Instruct`, `Qwen/Qwen2.5-7B-Instruct`, `TinyLlama/TinyLlama-1.1B-Chat-v1.0:featherless-ai`.

### Custom (self-hosted API)

```bash
export LITELLM_BASE_URL="http://localhost:8000/v1"
export TQA_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="local-vllm"
uv run python benchmarks/run_benchmark.py --benchmark mmlu --model "my-model-id"
```

Works with vLLM, Ollama (`/v1`), LiteLLM, or any OpenAI-compatible chat server. TruthfulQA reads `TQA_BASE_URL` before `LITELLM_BASE_URL` — set both for CLI hosted/custom runs.

On `/benchmarks/new`, choose **Custom**: model id, base URL (localhost, private IP, or `*.duke.edu` only), optional API key.

**Example custom inputs:** `my-finetune-v2` + `http://localhost:8080/v1`; `llama3.1` + `http://localhost:11434/v1` (Ollama).

## Benchmark catalog

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