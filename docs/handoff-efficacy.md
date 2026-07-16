# Hand-off — Efficacy pillar (Eval)

Short orientation for whoever picks this up. Deep detail lives in the docs linked
below; this page covers **what to know first** and **the things that aren't obvious
from the code**.

Live: **https://model-advisor.colab.duke.edu** · Code: `evaluator/`, `frontend/eval_*.py`

---

## 1. What it does

Scores a model's answers on **10 Duke task suites**, two ways:

| Mode | Suites | How it's scored |
|---|---|---|
| **LLM-as-judge** (6) | it_support, policy_qa, summarization, email_drafting, tutoring, plain_language | Graded against a YAML rubric by a judge model |
| **Execution** (4) | sql_duke, json_duke, numeric_duke, tool_use_duke | The answer is **run and checked** — no judge, no judge bias |

The judge is always a **different model family** than the candidate (MT-Bench rule),
at temperature 0. Every run logs cost, latency, and tokens, writes JSONL to
`evaluator/results/`, and is ingested into Postgres, which backs the dashboard.

## 2. The one rule that matters

**The eval contract is frozen.** `evaluator/frozen_contract.yaml` SHA-pins 37 artifacts
(schema, metrics, suites, rubrics, prompts); `unit_tests/test_contract_freeze.py` fails
if any of them changes.

This is deliberate: editing a suite or rubric in place silently breaks score
comparability with every run that came before it. **To evolve the contract: add a new
versioned file** (`foo_v2.jsonl`), then append it to the manifest and bump
`artifact_count` — never re-hash an existing pin. The 2026-07-16 follow-up freeze
(tool_use) is the worked example.

## 3. How to read the scores

The judge was validated against human raters (`docs/validation-study.md`):

- **Judge vs. human: Cohen's κ = 0.23** — level with the **human ceiling** (rater-vs-rater
  Fleiss' κ = 0.27). Both "fair."
- Read that as: **the judge is about as good as an average human rater** on a subjective
  task — a usable stand-in, not an oracle. Open-ended scores are **directional, not absolute**.
- The judge flips its pick **45%** of the time when two answers are swapped. This is
  controlled by judging every pair in **both display orders** (flips collapse to "tie").
  Don't remove that.
- Execution-scored suites have no such caveat — they're the ground-truth anchor.

## 4. Gotchas (these cost real time to rediscover)

- **The pillar dependency groups conflict.** `garak` (safety) pins `datasets<4`;
  benchmarks need `datasets>=5`. `tool.uv.conflicts` in `pyproject.toml` enforces
  "install at most ONE pillar group." So you **cannot** run the safety pillar in the
  eval venv — trigger safety **from the website** (it runs in its own container). See
  [`safety/README.md`](../safety/README.md).
- **Postgres needs the Duke VPN.** Without it, the frontend silently falls back to
  reading JSONL off disk — which on a dev laptop looks like "missing data" (the catalog
  under-counts, because scan/safety artifacts only exist in the DB). The **live site is
  the source of truth** for any number you're about to quote.
- **Ingest needs `PYTHONPATH`**: `PYTHONPATH=. uv run python evaluator/db/load_results.py --apply`
  (dry-run without `--apply`). It's idempotent.
- **The gateway budget is a shared key.** Batch jobs exhaust it fast; a 429
  `budget_exceeded` shows up as a run full of empty/failed rows. Check the budget before
  blaming the code.
- **Reasoning models need headroom.** They spend the `max_tokens` budget on hidden
  thinking and return empty visible text. `candidate.py` treats an empty response as a
  failure (never cached) and retries; slow models also get one timeout retry. If a suite
  comes back empty, raise `--max-tokens` before anything else.
- **Open-weight/HF models** are served on the DCC GPU via vLLM and torn down after the
  run — currently through an **individual account**, which production must replace with a
  service account.
- **Deployment runs the Flask dev server**, so a redeploy causes transient 500s. Not a
  code bug; production wants gunicorn.

## 5. Where to pick up

1. **Service account + budget** — unblocks open-weight evaluation for every pillar and
   continuous re-scanning. Needs a Duke owner, not more code.
2. **Duke-office-validated task references** — today's references are hand-written
   stopgaps, so rankings are *pipeline validation*, not an authoritative Duke benchmark.
   This is the single highest-value upgrade to credibility.
3. **Widen the validation study** — 6 raters / 60 comparisons is a calibration sample;
   more raters tightens κ.
4. **Robustness + multi-turn** — the third HELM bucket, and everything today is single-turn.

## 6. Key files

| Path | Role |
|---|---|
| `evaluator/frozen_contract.yaml` | The SHA-pinned contract — read §2 before touching |
| `evaluator/schemas.py` | `EvaluationResult` — the result-row contract |
| `evaluator/runner.py` | Orchestrates a suite run → JSONL |
| `evaluator/candidate.py` · `judge.py` | Gateway calls; rubric-aware judging |
| `evaluator/execution_eval.py` | Run-and-check scoring (SQL/JSON/numeric/tool-use) |
| `frontend/eval_launch.py` | `SUITES`, `JUDGE_MODELS`, browser launch (allowlist = the security boundary) |
| `frontend/eval_run_data.py` | What the eval page shows (dedupe, staleness, cost/perf) |
| `scripts/run_all_models.py` | Batch sweep (`--skip-existing` to resume) |
| `docs/validation-study.md` | The κ study — cite this when asked "can you trust the judge?" |

**See also:** [`cli.md`](cli.md) (every command) · [`architecture.md`](architecture.md) ·
[`data-model.md`](data-model.md) · [`track-b-framework.md`](track-b-framework.md) ·
[`rubric-design.md`](rubric-design.md) (adding a rubric) · [`suite-readiness.md`](suite-readiness.md)
