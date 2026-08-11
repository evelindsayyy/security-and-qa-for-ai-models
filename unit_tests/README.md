# Unit tests

Automated checks for `scanner/` (no Docker, no HF downloads).

| Directory | Role |
|-----------|------|
| `unit_tests/` | Unit tests (this folder) |
| `testing/` | Manual gateway/eval spikes |
| `scanner/experiments/` | Manual scanning tool spikes |

```bash
uv sync --group dev
uv run ruff check .
uv run python -m unittest discover -s unit_tests -v
# or a single module:
uv run python -m unittest unit_tests.test_risk_scorer -v
```

**CI parity** (same as the GitHub Actions pipeline): [`docs/cli.md`](../docs/cli.md#tests-and-lint-matches-ci).

Tests mock gateway calls and default to `FRONTEND_LAUNCH_MODE=host` — no Docker or secrets required.

The repo has ~800 tests across 88 `test_*.py` modules (scanner, safety, eval, benchmarks, loaders, `*_db_data`, launchers, `api/`, `model_rollup`, `recommendation_rules`, `db_fallback`, `launch_registry`, routes, and `dbutils/`). Run the full suite with `discover` above rather than maintaining a per-module table here.

Fixtures: `unit_tests/fixtures/`. Live scan output: `scanner/output/` (gitignored on host).
