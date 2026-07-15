# scripts/

Repo-root helpers and standalone inference backends.

| Script | Purpose |
|--------|---------|
| [`apply-schemas.sh`](apply-schemas.sh) | Apply all four pillar Postgres DDL files; `--bootstrap` also runs `api.ingest bootstrap --apply` |

Standalone inference helpers for **non-gateway** model backends. The pillars
(scanner, safety, evaluator) target the Duke AI Gateway by default; these scripts
are the groundwork for the optional second backend in
[`docs/architecture.md`](../docs/architecture.md) (open-source weights served on GPU).

| Dir | Backend | Purpose |
|-----|---------|---------|
| [`dcc/`](dcc/README.md) | Duke Compute Cluster (SLURM + vLLM) | Start/stop a GPU vLLM server for an open-weight HF model and send prompts over its OpenAI-compatible API. **Today:** evaluator CLI. **Planned:** safety + benchmarks. |
| [`azure/`](azure/README.md) | Microsoft Foundry | One-shot chat against a deployed Foundry model via its OpenAI-compatible endpoint. |

Both expose an **OpenAI-compatible** endpoint, so the pillars can eventually point
at them with the same client code used for the gateway — only the base URL and
credentials change. Foundry config lives in `FOUNDRY_*` in the repo-root `.env`;
the DCC server is reached at the cluster node URL printed by `dcc/wait_vllm.sh`.

These are examples/spikes for the optional second backend in
[`docs/architecture.md`](../docs/architecture.md). Evaluator CLI wiring exists
today; safety and benchmarks UI/CLI parity is on the roadmap.

## Dev tooling

| Script | Purpose |
|--------|---------|
| [`dev/fake_vllm.py`](dev/fake_vllm.py) | Minimal stand-in OpenAI-compatible server (Flask) — answers `/health` and `/v1/chat/completions` with a fixed canned reply. Lets you exercise `safety.run --hf-repo ... --endpoint http://localhost:PORT/v1` end-to-end without a GPU or an active `dcc/` session. Proves the pipeline's plumbing works; says nothing about whether a real model is safe. Promptfoo's eval runs inside its own Docker container, so its `--endpoint` must use the Docker bridge gateway IP (e.g. `http://172.17.0.1:PORT/v1` on Linux), not `localhost` — see the script's docstring. |
