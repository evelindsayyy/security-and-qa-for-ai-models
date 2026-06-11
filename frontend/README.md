# Frontend (`frontend/`)

Progress viewer for the Duke model nutrition label. Loads JSON from local pipeline output directories; eval, scan, and safety pillars also support **browser-launched runs** (subprocess + live polling), mirroring Grace’s evaluator pattern.

Production UI (week 6) will read from Postgres via `api/`. This draft reflects whatever is on disk under `scanner/output/`, `evaluator/results/`, `safety/output/`, and `testing/basic_tests/test_results/` (run outputs are gitignored locally).

## Run locally

```bash
uv sync
uv run flask --app frontend:create_app run --debug
# or: python main.py
```

## Routes

| Route | Purpose |
|-------|---------|
| `/` | Hub — scan/eval/safety counts (no gateway model list) |
| `/models` | Live gateway catalog only (`GET /v1/models`) |
| `/scans` | HF `scan_result.json` rows from `scanner/output/` |
| `/scans/new`, `/scans/start` | Start an allowlisted HF scan from the browser |
| `/scans/<slug>`, `/scans/<slug>/status` | Scan detail or in-progress polling |
| `/eval-run` | Aggregated efficacy runs from `evaluator/results/*.jsonl` |
| `/eval-run/new`, `/eval-run/start` | Start eval run (Grace) |
| `/eval-run/<slug>`, `.../status` | Eval detail or progress |
| `/safety` | Merged safety from `safety/output/*/merged_safety_result.json` |
| `/safety/new`, `/safety/start` | Start gateway safety run (`run_safety.sh`) |
| `/safety/<slug>`, `/safety/<slug>/status` | Safety detail or progress |
| `/benchmarks` | Jack’s benchmarks from `testing/basic_tests/test_results/` |

## Populate data

**Scanning:** run `python -m scanner scan <hf_id>` or use **Start a new scan** on `/scans`.

**Efficacy:** run `evaluator/runner.py` or use **Start a new run** on `/eval-run`.

**Safety:** run `safety/run_safety.sh` + merge, or use **Start a new run** on `/safety`.

**Benchmarks:** run scripts under `testing/basic_tests/` (TQA, IFEval, MMLU, ToMi, consistency).

Refresh the browser after new files appear; no restart needed.

## Layout

| Module | Role |
|--------|------|
| `gateway_catalog.py` | Live gateway ids via `GET /v1/models` (5 min cache) |
| `scan_data.py` / `scan_launch.py` | Load scans; launch HF scans |
| `eval_run_data.py` / `eval_launch.py` | Load eval JSONL; launch runner |
| `safety_data.py` / `safety_launch.py` | Load merged safety; launch `run_safety.sh` |
| `benchmark_data.py` | TQA, IFEval, consistency, MMLU, ToMi |
| `routes.py` | Flask routes |
| `templates/` | Jinja HTML |
| `static/style.css` | Shared styles — severity tiers use red/orange/yellow/green; tool badges are neutral grey |

## Safety overview (UI)

Each row shows the calibrated **tier** (`composite_tier`), the overall **pass
rate**, and a per-suite breakdown (Duke policy, Red-team, Garak). Models are
ordered highest-risk first (lowest composite score). The tier is a weighted
blend of suite pass rates escalated by Duke policy failures — tuned so
known-safe commercial models read `low`. See
[`safety/README.md`](../safety/README.md) for the calibration.

## Browser-launched runs

The "Start a new run" button on each pillar (scans, eval, safety) launches the
real CLI as a subprocess. **Starting a run wipes that model's prior outputs**
so the UI never blends stale and fresh JSON:

- Scans → `scanner/output/<slug>/`
- Eval → prior `*_<suite>_<candidate>.{jsonl,log}` for that model+suite
- Safety → `safety/output/<slug>/` + the per-tool `promptfoo`/`garak` dirs

The eval comparison table also de-dupes to the **latest run per
(candidate, judge, suite)** so superseded runs don't linger.

## Related docs

- [`docs/architecture.md`](../docs/architecture.md)
- [`scanner/README.md`](../scanner/README.md)
- [`evaluator/README.md`](../evaluator/README.md)
- [`safety/README.md`](../safety/README.md)
