# Evaluator (Track B)

Gateway efficacy via Duke LiteLLM. Schemas, candidate, and judge modules plus IT support task assets are in repo; runner wiring in progress. Framework: [`docs/track-b-framework.md`](../docs/track-b-framework.md).

## Layout

| Path | Role |
|------|------|
| `schemas.py` | `EvaluationResult` row contract (G-Eval dimensions, operational metrics, `schema_version`) |
| `_gateway.py` | Shared OpenAI client → `DUKE_GATEWAY_URL` / `DUKE_GATEWAY_KEY` |
| `candidate.py` | `generate_candidate()` — gateway call + file cache under `cache/candidates/` |
| `judge.py` | `judge_response()` — LLM-as-judge vs rubric + cache under `cache/judges/` |
| `compare_judges.py` | Spike: compare judge models on sample rows |
| `tasks/it_support_v1.jsonl` | IT support questions (v1 suite) |
| `tasks/rubrics/it_support.yaml` | Rubric dimensions + evaluation steps |
| `prompts/system/it_support_v1.txt` | System prompt template |
| `prompts/judge/reference_based_v1.txt` | Reference-based judge template |
| `metrics.yaml` | Suite → metric mapping (ROUGE-L etc.) |

Schedule and GitLab issues: [`docs/track-b-framework.md`](../docs/track-b-framework.md), [`.gitlab/gitlab-transfer.md`](../.gitlab/gitlab-transfer.md) (local).
