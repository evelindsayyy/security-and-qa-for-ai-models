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
Hugging Face model served by your own **OpenAI-compatible** endpoint (a local
vLLM server, or one launched on the DCC via [`scripts/dcc/`](../scripts/dcc/README.md)).

The model id is the HF repo (e.g. `Qwen/Qwen3-0.6B`); `model_client` auto-routes
it to the right provider based on the base URL (a remote vLLM host becomes
`openai/<repo-id>`).

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

Caveats: the model must be **provider-backed for chat completion** (check the
"Inference Providers" widget on its HF model page); there's a metered cost /
limited free tier; and only the bare `org/model` id is supported here (not the
`org/model:provider` pin).

### CLI

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