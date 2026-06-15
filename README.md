# Security & QA Tools for Duke's AI Models

Code+ 2026 — Duke Office of Information Technology

Automated **nutrition labels** for Duke AI Gateway models: security (scanning + safety) and efficacy (Duke task suites + public benchmarks).

| Pillar | Question |
|--------|----------|
| **Scanning** | Can model files or dependencies compromise Duke infrastructure? |
| **Safety** | Can the model be misused or violate policy at inference time? |
| **Efficacy** | How well does it perform on Duke-relevant and standard benchmark tasks? |

**Docs:** [`docs/README.md`](docs/README.md) · **Tracks:** [A (security)](docs/track-a-framework.md) · [B (efficacy)](docs/track-b-framework.md)

---

## Quick start

```bash
uv sync
cp .env.example .env   # paste DUKE_GATEWAY_KEY from dashboard.ai.duke.edu
uv run flask --app frontend:create_app run --debug
# → http://127.0.0.1:5000  (/scans  /safety  /eval-run  /benchmarks  /models)
```

---

## Repository layout

```
scanner/              Track A — HF artifact scanning
safety/               Track A — promptfoo + garak red team
evaluator/            Track B — Duke efficacy (LLM-as-judge, runner.py)
benchmarks/           Track B — public benchmarks (TruthfulQA, IFEval, MMLU, …)
gateway/              Live gateway catalog (GET /v1/models)
frontend/             Nutrition-label UI
tasks/                Rubrics and suite placeholders
scripts/              Foundry and DCC/vLLM example workflows
testing/              Manual spikes (gateway smoke, legacy paths)
docs/                 Architecture, data model, tool matrix
api/                  Flask REST API (planned — persistence layer)
unit_tests/           Automated tests
```

Runtime outputs are gitignored (`scanner/output`, `evaluator/results`, `benchmarks/results`, `safety/output`). Each pillar README documents its paths.

---

## CLI (one command per pillar)

**Scan** (HF repo → `scanner/output/<slug>/scan_result.json`):

```bash
docker compose --env-file .env -f scanner/docker/compose.yml \
  run --rm scanner python -m scanner scan gpt2
```

**Safety** (gateway model → merged JSON under `safety/output/`):

```bash
./safety/run_safety.sh "GPT 4.1 Mini"
```

**Efficacy** (candidate + judge → `evaluator/results/*.jsonl`):

```bash
docker compose --env-file .env -f evaluator/docker/compose.yml \
  run --rm evaluator python runner.py \
  --candidate-model "GPT 4.1 Mini" --judge-model "Llama 4 Maverick"
```

**Public benchmark** (TruthfulQA, IFEval, … → `benchmarks/results/`):

```bash
docker compose --env-file .env \
  -f benchmarks/docker/compose.yml run --rm benchmarks \
  python run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"
```

Pillar details: [`scanner/README.md`](scanner/README.md) · [`safety/README.md`](safety/README.md) · [`evaluator/README.md`](evaluator/README.md) · [`benchmarks/README.md`](benchmarks/README.md) · [`frontend/README.md`](frontend/README.md)

---

## Gateway catalog

Single live source — [`gateway/`](gateway/README.md) (`GET /v1/models`, 5‑min cache):

```bash
uv run python -m gateway          # grouped listing
uv run python -m gateway --json   # machine-readable
```

Frontend `/models` and all launch dropdowns read this package. Reference table: [`docs/gateway-models.md`](docs/gateway-models.md).

---

## Environment

See `.env.example`. Never commit `.env`.

- `DUKE_GATEWAY_URL`, `DUKE_GATEWAY_KEY` — gateway endpoint + token (aliases: `OPENAI_BASE_URL`, `OPENAI_API_KEY`)
- `HF_TOKEN` — gated HF models (scanning)
- `FRONTEND_LAUNCH_MODE=host` — skip Docker for browser launches

---

## Links

- [Code+ project page](https://codeplus.duke.edu/project/security-quality-assurance-tools-dukes-ai-models/)
- [GitLab](https://gitlab.oit.duke.edu/codeplus/security-and-qa-for-ai-models)
- [Duke AI Suite](https://oit.duke.edu/ai-suite) · [Gateway dashboard](https://dashboard.ai.duke.edu)
