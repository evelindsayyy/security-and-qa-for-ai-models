# Unit tests

Automated checks for `scanner/` (no Docker, no HF downloads).

| Directory | Role |
|-----------|------|
| `unit_tests/` | Unit tests (this folder) |
| `testing/` | Manual gateway/eval spikes |
| `scanner/experiments/` | Manual scanning tool spikes |

```bash
uv run python -m unittest unit_tests.test_risk_scorer -v
```

Fixtures: `unit_tests/fixtures/`. Live scans: `scanner/output/` (DGX, gitignored).
