# Documentation

Project guides & info. **GitLab:** [`.gitlab/README.md`](../.gitlab/README.md). 

| Document | Role |
|----------|------|
| [`team-tracks.md`](team-tracks.md) | Tracks, phases, deployment context |
| [`track-a-framework.md`](track-a-framework.md) | Scanning + safety → security pillar |
| [`track-b-framework.md`](track-b-framework.md) | Efficacy pillar (Track B) |
| [`gateway-models.md`](gateway-models.md) | Gateway catalog; HF scan list; test tiers |
| [`architecture.md`](architecture.md) | System design, `api/`, `frontend/`, deployment |
| [`cli.md`](cli.md) | All CLI commands (UI, pillar jobs, tests, ingest) |
| [`docker.md`](docker.md) | Docker model — layers, sibling launches, CI |
| [`../frontend/README.md`](../frontend/README.md) | Nutrition label UI |
| [`data-model.md`](data-model.md) | Postgres plan — tables, example fields, JSON → DB path |
| [`../dbutils/README.md`](../dbutils/README.md) | Shared Postgres ingest helpers |
| [`tool-stack.md`](tool-stack.md) | Tools and rationale |
| [`../scripts/README.md`](../scripts/README.md) | Non-gateway inference helpers (DCC/vLLM, Azure Foundry) |

**Pillar READMEs**

| Path | Track |
|------|-------|
| [`scanner/README.md`](../scanner/README.md) | A — HF scanning |
| [`safety/README.md`](../safety/README.md) | A — inference safety |
| [`evaluator/README.md`](../evaluator/README.md) | B — Duke efficacy (`runner.py`) |
| [`benchmarks/README.md`](../benchmarks/README.md) | B — public benchmarks |
| [`gateway/README.md`](../gateway/README.md) | Shared — live catalog + `ANNOTATIONS` |
| [`frontend/README.md`](../frontend/README.md) | Nutrition-label UI |
| [`testing/README.md`](../testing/README.md) | Manual spikes |
| [`unit_tests/README.md`](../unit_tests/README.md) | Automated tests |
