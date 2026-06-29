# Evaluator (Track B)

Gateway **efficacy** evaluation via Duke task suites and an LLM-as-judge (`runner.py`).

Public academic benchmarks (TruthfulQA, IFEval, MMLU, …) are a sibling pillar — see [`../benchmarks/`](../benchmarks/README.md) (`/benchmarks` tab).

Launch from the browser or CLI; both use Docker by default. CLI reference: [`docs/cli.md`](../docs/cli.md).

## Quickstart

**1. Environment** (repo root `.env`):

```bash
DUKE_GATEWAY_URL=https://litellm.oit.duke.edu/v1   # confirm with OIT
DUKE_GATEWAY_KEY=<your litellm api key>
```

**2. Install and run** (from repo root):

```bash
uv sync
cd evaluator
uv run python runner.py \
  --candidate-model "gpt-5-chat" \
  --judge-model "Llama 4 Maverick"
```

**3. Output** (gitignored):

- `evaluator/results/<UTC>_<suite>_<candidate>.jsonl` — one `EvaluationResult` per line
- `evaluator/results/<same>_trace.jsonl` — raw responses for debugging
- `evaluator/cache/` — candidate/judge caches (re-runs are cheap). **Docker:** `evaluator/cache` is bind-mounted in `evaluator/docker/compose.yml` so the container user (host UID/GID) can write cache files.

**Docker (browser or CLI):**

```bash
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env \
  -f evaluator/docker/compose.yml run --rm evaluator \
  python runner.py --candidate-model "GPT 4.1 Mini" --judge-model "Llama 4 Maverick" \
  --max-tokens 2000 --judge-max-tokens 2000
```

**4. Summarize** a run with the aggregator (positional path, plain stdout table):

```bash
uv run python aggregate.py results/<UTC>_<suite>_<candidate>.jsonl
```

Reports per-dimension means, weighted overall, mean + p95 latency, total tokens, total cost, and failure rate. Re-running the runner on the same `(candidate, judge)` is free — both sides are content-hashed in `cache/`.

## What to expect

A clean run on the IT support suite (`n = 12`) takes ~3 minutes wall-clock and a few cents of gateway budget. Sample numbers from four candidates, all judged by `Llama 4 Maverick`:

| candidate | overall | accuracy | completeness | policy | tone | total cost | note |
|---|---|---|---|---|---|---|---|
| gpt-5-chat | **4.79** | 4.83 | 4.50 | 4.92 | 3.00 | $0.028 | best on this rubric |
| GPT 4.1 Mini | 4.26 | 4.25 | 3.58 | 4.58 | 3.00 | $0.003 | 89% the quality at 11% the cost |
| Llama 4 Scout | 3.85 | 3.67 | 2.83 | 4.67 | 2.75 | $0.0014 | cheapest; same-family-as-judge caveat |
| gpt-5-mini | 3.29 | 2.67 | 2.67 | 4.50 | 2.00 | $0.013 | ⚠ all 12 responses empty (reasoning model on default `max_tokens`) |

Open `/eval-run` in the frontend to see the same comparison sorted best-first, with per-question rationales reachable by clicking the candidate name.

## Known limitations (v1)

- **Placeholder references.** `tasks/it_support_v1.jsonl` answers were drafted from publicly inferable Duke OIT facts (NetID, Cisco AnyConnect, Duo, SecureW2, Box, ePrint, OIT 919-684-2200). Scores against them are sufficient to validate the pipeline runs, not to draw conclusions about model quality. Replace with OIT-staff-written references before reporting scores as meaningful.
- **Reasoning models + low `max_tokens`.** GPT-5 reasoning variants (`gpt-5-mini`, `gpt-5-nano`, `o4-mini`) spend the full budget on hidden tokens and emit empty visible text. The runner records this honestly; the `/eval-run` table flags it as `⚠ N/n empty`. Defaults are now `--max-tokens 2000` and `--judge-max-tokens 2000`; reasoning models may still need 4000.
- **Tone ceiling on GPT-family candidates.** All three GPT candidates scored 3/3 on tone. `Llama 4 Scout` was the first to come off the ceiling (2.75). The anchor isn't broken — the test set is just uniformly easy on tone for OpenAI outputs.
- **Judge bias not corrected.** Position, verbosity, and self-preference biases are documented in `tasks/rubrics/it_support.yaml` limitations but not algorithmically corrected. The weeks 7-8 validation study against human raters will quantify them.

## Layout

| Path | Role |
|------|------|
| `schemas.py` | `EvaluationResult`, `DimensionScore`, `Adaptation`, `Operational` (`schema_version` 1.0.0) |
| `_gateway.py` | Shared OpenAI client → gateway URL/key |
| `candidate.py` | `generate_candidate()` per question |
| `judge.py` | `judge_response()` vs rubric YAML |
| `runner.py` | Full suite loop → JSONL |
| `compare_judges.py` | One-off judge A/B spike (not production) |
| `tasks/it_support_v1.jsonl` | 12 IT support questions |
| `tasks/rubrics/it_support.yaml` | G-Eval dimensions + weights |
| `prompts/` | System + judge templates |
| `metrics.yaml` | Future suite → metric mapping |


## Related docs

- [`docs/track-b-framework.md`](../docs/track-b-framework.md)
- [`docs/gateway-models.md`](../docs/gateway-models.md)
- [`frontend/README.md`](../frontend/README.md) — draft results viewer
