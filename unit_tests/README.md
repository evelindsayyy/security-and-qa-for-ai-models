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

**CI parity** (same as GitLab pipeline): [`docs/cli.md`](../docs/cli.md#tests-and-lint-matches-ci).

Tests mock gateway calls and default to `FRONTEND_LAUNCH_MODE=host` — no Docker or secrets required.

| Test module | Covers |
|-------------|--------|
| `test_path_safety` | Slug traversal guards |
| `test_scan_launch` | HF scan browser launch + Flask routes |
| `test_safety_launch` | Safety browser launch + Flask routes |
| `test_safety_data` | Merged safety summarize/detail |
| `test_promptfoo_exporter` | Promptfoo grading helpers |
| `test_garak_exporter` | Garak JSONL → SafetyRunResult |
| `test_garak_report_validation` | Garak report completeness, XDG env, ToxicCommentModel preflight |
| `test_safety_scorer` | Safety merge + tier calibration (committed fixtures) |
| `test_safety_launch` | Safety browser launch, stale locks, partial Garak warnings |
| `test_scanner_*` | ModelAudit filters, dependency merge, secret parse, paths |
| `test_run_benchmark` | Benchmark slug/stem validation |

Fixtures: `unit_tests/fixtures/`. Live scan output: `scanner/output/` (gitignored on host).
