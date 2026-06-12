# Testing (manual spikes)

Pre-production scripts for gateway connectivity and one-off experiments.
**Not** automated tests → [`unit_tests/`](../unit_tests/). **Not** production pillars.

## Layout

| Path | Purpose |
|------|---------|
| `test_gateway.py` | Gateway smoke (OpenAI SDK) |
| `gateway/` | Gateway spike scripts — see [`gateway/README.md`](gateway/README.md) |
| `eval/` | Early TruthfulQA spike (data only) |
| `basic_tests/` | **Moved** → [`benchmarks/`](../benchmarks/) |
| `scanning/` | Pre-scanner spikes (superseded by [`scanner/`](../scanner/)) |

## Gateway smoke

```bash
uv run python testing/test_gateway.py
```

## Benchmarks & efficacy

- **Public benchmarks** (TruthfulQA, IFEval, MMLU, …): [`benchmarks/`](../benchmarks/)
- **Duke efficacy eval** (LLM-as-judge): [`evaluator/`](../evaluator/)
