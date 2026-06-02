# Testing (manual spikes)

**Pre-production scripts** for gateway and eval — run tools, inspect output, learn formats.  
**Not** automated unit tests → [`unit_tests/`](../unit_tests/).  
**Not** HF scanning → [`scanner/`](../scanner/).

## Layout

| Path | Purpose |
|------|---------|
| `test_gateway.py` | Gateway smoke (OpenAI SDK) |
| `gateway/` | Gateway spike scripts |
| `eval/` | Track B efficacy spikes (TruthfulQA, etc.) |
| `basic_tests/` | Legacy TruthfulQA/compare scripts (optional) |

## Gateway smoke

```bash
python testing/test_gateway.py
```

## Eval

See [`eval/README.md`](eval/README.md).
