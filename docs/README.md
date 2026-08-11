# Documentation

Project guides. **GitHub Actions:** [`.github/OPERATIONS.md`](../.github/OPERATIONS.md).

## Core

| Document | Role |
|----------|------|
| [`cli.md`](cli.md) | **All CLI commands** — UI (`run.sh` / `main.py`), SSH, pillars, ingest, tests |
| [`architecture.md`](architecture.md) | System design, data flow, deployment |
| [`docker.md`](docker.md) | Docker layers, assets, CI, Caddy HTTPS |
| [`../docker/README.md`](../docker/README.md) | Compose scripts, production setup, troubleshooting |
| [`data-model.md`](data-model.md) | Postgres schema and ingest mapping |
| [`gateway-models.md`](gateway-models.md) | Gateway catalog and scan tiers |

## Tracks and tools

| Document | Role |
|----------|------|
| [`team-tracks.md`](team-tracks.md) | Tracks, phases, deployment context |
| [`track-a-framework.md`](track-a-framework.md) | Scanning + safety |
| [`track-b-framework.md`](track-b-framework.md) | Evaluator + benchmarks |
| [`handoff-efficacy.md`](handoff-efficacy.md) | **Eval pillar hand-off** — start here: the frozen contract, how to read the scores, gotchas |
| [`validation-study.md`](validation-study.md) | Judge vs. human agreement (κ) — the evidence the judge is trustworthy |
| [`tool-stack.md`](tool-stack.md) | Tools and rationale |

## Packages

| Path | Role |
|------|------|
| [`../frontend/README.md`](../frontend/README.md) | UI, islands, API curl examples |
| [`../auth/README.md`](../auth/README.md) | Duke OIDC login |
| [`../api/README.md`](../api/README.md) | REST under `/api` |
| [`../dbutils/README.md`](../dbutils/README.md) | Ingest helpers |
| [`../scripts/README.md`](../scripts/README.md) | DCC vLLM, Azure helpers |

**Pillar READMEs:** [`scanner/`](../scanner/README.md) · [`safety/`](../safety/README.md) ·
[`evaluator/`](../evaluator/README.md) · [`benchmarks/`](../benchmarks/README.md) ·
[`personality/`](../personality/README.md) · [`gateway/`](../gateway/README.md)

**Tests:** [`testing/README.md`](../testing/README.md) · [`unit_tests/README.md`](../unit_tests/README.md)
