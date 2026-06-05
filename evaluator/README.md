# Evaluator (Track B)

Gateway **efficacy** evaluation via Duke LiteLLM: candidate generation, LLM-as-judge scoring, and JSONL results aligned with [`docs/data-model.md`](../docs/data-model.md).

## Status

| Component | Status |
|-----------|--------|
| `schemas.py`, `candidate.py`, `judge.py`, `_gateway.py` | In repo |
| `runner.py` (IT support E2E) | In repo |
| IT support suite + rubric + prompts | In repo |
| Smoke run on one gateway model | Done when `evaluator/results/*.jsonl` exists |
View aggregated runs in the draft UI: `uv run flask --app frontend:create_app run` → `/eval-run`.

## Quickstart

**1. Environment** (repo root `.env` or shell):

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
- `evaluator/cache/` — candidate/judge caches (re-runs are cheap)

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
