# Efficacy evaluation spikes (Track B)

Spike scripts before `evaluator/` (week 3+). Goal: run tools, inspect output, map to [`docs/data-model.md`](../../docs/data-model.md) (`eval_runs`, `eval_results`).

## TruthfulQA MCQ (week 2)

| Path | Role |
|------|------|
| `truthfulqa/evaluate_truthfulqa_mcq.py` | Multi-model MCQ eval via OpenAI-compatible gateway |
| `truthfulqa/datasets/TruthfulQA.csv` | Dataset |
| `truthfulqa/models.gateway.json` | Provider aliases → LiteLLM `model` strings |
| `output/samples/truthfulqa_w2_summary.csv` | Committed W2 summary (n=50) |
| `output/` | Regenerated detail CSVs (gitignored) |

**Week 2 results (n=50, seed=42):**

| provider_name | model | accuracy |
|---------------|-------|----------|
| duke-gpt54 | gpt-5.4 | 0.90 |
| duke-mistral | Mistral on-site | 0.74 |
| duke-llama33 | Llama 3.3 | 0.62 |

```bash
export DUKE_AI_GATEWAY_API_KEY=...
cd testing/eval/truthfulqa
python evaluate_truthfulqa_mcq.py --limit 50
```

**Next (W3):** Move patterns into `evaluator/`; run **MVP suites** on one gateway model (not only IT support).

Framework: [`docs/track-b-framework.md`](../../docs/track-b-framework.md). GitLab: [`.gitlab/README.md`](../../.gitlab/README.md).
