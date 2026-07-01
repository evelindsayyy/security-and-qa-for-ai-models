# Data model

Target **PostgreSQL** schema for [`api/`](../api/README.md). Each pillar writes **JSON artifacts** with shapes defined in code (Pydantic or dataclass); **ingest** loads them into Postgres via **psycopg** — see [`architecture.md`](architecture.md#json--postgres-summary) and [`docs/cli.md`](cli.md).

Catalog keys: [`gateway-models.md`](gateway-models.md).

---

## Principles

- One **`models`** row per gateway model (`gateway_model_id`; optional `hf_repo` when weights are on-prem).
- **Scanning:** `models` → `scans` → `findings` (HF artifact jobs only).
- **Safety:** `models` → `safety_runs` → `safety_findings` (gateway inference).
- **Efficacy — Duke suites:** `task_suites` → `eval_runs` → `eval_results` (LLM-as-judge; cost/latency/tokens).
- **Efficacy — public benchmarks:** `benchmark_runs` (IFEval, TruthfulQA, MMLU, …) — shared run envelope, benchmark-specific detail in JSONB.
- **UI reads normalized fields;** investigators drill into `tool_results`, `detail`, or `metrics` JSONB.

```text
users ── user_run_links
models ──┬── scans ── findings
         ├── safety_runs ── safety_findings
         ├── eval_runs ── eval_results
         └── benchmark_runs
task_suites ── eval_runs
```

Each pillar run table also has: `visibility` (`public`|`private`), `owner_user_id` → `users`, `config_fingerprint`, `config_json`. DDL: [`db/auth_schema.sql`](../db/auth_schema.sql).

---

## `models`

Gateway catalog anchor (and optional HF repo for on-prem).

| Column | Type (sketch) | Example |
|--------|---------------|---------|
| `id` | UUID | `a1b2c3d4-…` |
| `gateway_model_id` | string, unique | `gpt-4.1-mini` |
| `display_name` | string | `GPT 4.1 Mini` |
| `provider` | string | `openai` |
| `hf_repo` | string, nullable | `null` (cloud) or `meta-llama/Llama-3.3-70B-Instruct` |
| `deployment_context` | JSONB, nullable | see below |
| `is_active` | bool | `true` |
| `created_at` | timestamptz | `2026-05-28T12:00:00Z` |

---

## `scans` (Track A — scanning)

> **Authoritative DDL:** `scanner/db/scan_schema.sql` (implemented; loader:
> `scanner/db/load_scans.py`, idempotent, dry-run by default, uses `dbutils/`).
> Idempotency: `UNIQUE (hf_repo, completed_at)` where `completed_at` =
> `scan_metadata.scanned_at`. Shared `models` FK on `scans.model_id` deferred.

One HF repo inspection job.

| Column | Example |
|--------|---------|
| `id` | UUID |
| `model_id` | FK → `models.id` (via `hf_repo` or linked catalog row) |
| `hf_repo` | `gpt2` |
| `status` | `queued` \| `running` \| `complete` \| `failed` |
| `overall_risk_score` | `42` (0–100) |
| `severity_tier` | `low` \| `medium` \| `high` \| `critical` |
| `scanned_files` | JSON array | `["pytorch_model.bin", "config.json"]` |
| `tool_results` | JSONB | `{"modelscan": {...}, "fickling": {...}, "modelaudit": {...}, "dependencies": {...}, "secrets": {...}}` |
| `scan_metadata` | JSONB | `{"duration_s": 120, "worker": "dgx-01"}` |
| `started_at` / `completed_at` | timestamptz | |

**`findings`** (child rows — one issue per actionable item):

| Column | Example |
|--------|---------|
| `id` | UUID |
| `scan_id` | FK |
| `source` | `modelscan` \| `fickling` \| `modelaudit` \| `pip_audit` \| `osv` \| `trufflehog` |
| `title` | `pickle safety signal from fickling` |
| `severity` | `low` |
| `file_path` | `pytorch_model.bin` |
| `description` | text |
| `raw_tool_severity` | `LIKELY_UNSAFE` |
| `remediation` | nullable text |
| `corroborated_by` | string array, nullable | `["fickling"]` when ModelAudit and Fickling agree on same file/signal |

Shapes: `scanner/schemas.py` (`ScanResult`, `Finding`).

---

## `safety_runs` / `safety_findings` (Track A — safety)

> **Authoritative DDL:** `safety/db/safety_schema.sql` (implemented; loader:
> `safety/db/load_safety.py`, idempotent, dry-run by default, uses `dbutils/`).
> Idempotency: `UNIQUE (gateway_model_id, redteam_profile, completed_at)`.
> Shared `models` FK on `safety_runs.model_id` deferred (same stance as scans).

One merged red-team result per gateway model per profile. Multiple probe suites
(garak, promptfoo policy, promptfoo red-team) are merged into a single
`merged_safety_result.json` artifact at `safety/output/<slug>/<profile>/` and
loaded as one `safety_runs` row with child `safety_findings` rows.

**`safety_runs`:**

| Column | Example |
|--------|---------|
| `id` | UUID |
| `model_id` | FK → `models.id` (nullable; deferred until shared models table exists) |
| `gateway_model_id` | `gpt-4.1-mini` |
| `redteam_profile` | `base` \| `education` \| `healthcare` \| … |
| `display_name` | `GPT 4.1 Mini` |
| `status` | `complete` |
| `deployment_context` | JSONB — `{"deployment_type": "chatbot", "has_guardrails": true, …}` (ITSO context) |
| `summary_pass_rate` | `0.85` — fraction of findings with `passed=true` across all suites |
| `safety_tier` | `low` \| `medium` \| `high` \| `critical` — Duke policy headline (promptfoo_duke_policy_v1) |
| `adversarial_tier` | `low` \| `medium` \| `high` \| `critical` — worst failed severity across garak + red-team |
| `composite_tier` | `low` \| `medium` \| `high` \| `critical` — calibrated headline (see `safety_scorer.py`) |
| `composite_score` | `0.85` — weighted pass rate used to rank models |
| `missing_suites` | JSONB array — suites expected but absent (skipped/failed runs), e.g. `["promptfoo_duke_policy_v1"]` |
| `runs` | JSONB array of `SafetyRunSummary` — one entry per probe suite with per-suite pass rate and probe ids |
| `tool_results` | JSONB — raw tool metadata keyed by suite, e.g. `{"garak_subset_v1": {"garak": {"run_id": "…"}}}` |
| `started_at` / `completed_at` | timestamptz |
| `created_at` | timestamptz — row insertion time |

**`safety_findings`** (normalized probe outcomes, child of `safety_runs`):

| Column | Example |
|--------|---------|
| `id` | UUID |
| `run_id` | FK → `safety_runs.id` ON DELETE CASCADE |
| `finding_key` | `c515df9a-…` — `SafetyFinding.id` UUID assigned at merge time |
| `category` | `smoke` \| `policy` \| `jailbreak` \| `leakage` \| `toxicity` |
| `source` | `garak` \| `promptfoo` \| `duke_probe` |
| `passed` | `true` = model resisted the probe; `false` = failure |
| `severity` | `low` \| `medium` \| `high` \| `critical` |
| `title` | `academic integrity — graded submission request` |
| `description` | text — pass/fail summary from the tool |
| `probe_id` | `duke.policy.003` \| `garak.apikey` |
| `probe_suite` | `garak_subset_v1` \| `promptfoo_duke_policy_v1` \| `promptfoo_duke_redteam_v1` |
| `corroborated_by` | JSONB string array — other tools that failed the same category, e.g. `["garak"]`; null otherwise |

Pydantic types: `safety/schemas.py` (`MergedSafetyResult`, `SafetyFinding`, `SafetyRunSummary`).

---

## `task_suites` / `eval_runs` / `eval_results` (Track B — Duke efficacy)

> **Authoritative DDL: `evaluator/db/efficacy_schema.sql`** (implemented week 4;
> loader: `evaluator/db/load_results.py`, idempotent, dry-run by default).
> The tables below reflect what is implemented; columns marked *planned* are
> agreed direction but not yet in the DDL.

**`task_suites`** — one row per (suite, version); `UNIQUE (suite_key, version)`:

| Column | Example |
|--------|---------|
| `id` | UUID |
| `suite_key` | `it_support` \| `policy_qa` \| `summarization` |
| `version` | `v1` \| `v1.1` (suffix of `task_suite_version`) |
| `yaml_path` | `tasks/rubrics/it_support.yaml` (evaluator-relative) |
| `rubric_version` | `it_support_v1` |

**`eval_runs`** — one row per results JSONL; **PK reuses the file's
`evaluation_run_id` UUID** (gives the loader free idempotency):

| Column | Example |
|--------|---------|
| `id` | UUID (= `evaluation_run_id` from the JSONL) |
| `suite_id` | FK → `task_suites` |
| `gateway_model_id` | `gpt-4.1-mini` | |
| `judge_model` | `Llama 4 Maverick` | LLM-as-judge |
| `inference_backend` | `gateway` \| `dcc` | In JSONL `adaptation` today (CLI sets `dcc`); Postgres column *planned* |
| `hf_repo` | nullable | Open-weight HF id when `inference_backend=dcc` |
| `status` | `complete` |
| `aggregate_score` | float — mean of per-question `overall` |
| `latency_p50_ms` / `latency_p95_ms` | int |
| `tokens_in_total` / `tokens_out_total` | int |
| `cost_usd_total` | NUMERIC(12,6) — exact, never float |
| `adaptation` | JSONB — full how-it-was-run metadata (temperature, max_tokens, prompt/rubric versions); kept as JSONB so the table doesn't churn when `Adaptation` gains fields |
| `tool_results` | JSONB — optional raw judge logs (not loaded yet; traces stay on disk) |
| `source_file` | the JSONL filename — traceability + the frontend's slug key |
| `started_at` / `completed_at` | timestamptz |

**`eval_results`** — one row per question (**Option A**: per-dimension judge
scores live inside `detail`, so rubrics with different dimensions share one
table); `UNIQUE (eval_run_id, task_id, metric)`:

| Column | Example |
|--------|---------|
| `id` | UUID |
| `eval_run_id` | FK (ON DELETE CASCADE) |
| `task_id` | string — `it-support-001` |
| `metric` | `judge_score` today; `rouge_l` etc. land as extra rows for the same task (summarization suite) |
| `score` | the rubric-weighted `overall`; NULL when failed |
| `candidate_failed` / `judge_failed` | booleans — failed questions are queryable, never dropped |
| `latency_ms`, `tokens_in` / `tokens_out`, `cost_usd` | per-question operational |
| `detail` | JSONB — `{"candidate_response", "scores": {dim: {score, rationale}}, "error", "schema_version"}` |

Note: the sketched `eval_results.model_id` FK was dropped — model identity
lives on `eval_runs.gateway_model_id`; a FK to the shared `models` table can
be added once that table exists (cross-team decision pending).

Row contract: `evaluator/schemas.py` (`SCHEMA_VERSION` is carried into
`detail` for future migrations).

---

## `benchmark_runs` (Track B — public benchmarks)

Public academic benchmarks from `benchmarks/` (IFEval, TruthfulQA, MMLU, ToMi, consistency). **Separate from `eval_runs`:** benchmark-defined automatic scoring (accuracy, pass-rate, BERTScore), not an LLM judge; own frontend tab.

One shared table — each benchmark produces the same run envelope (`frontend/benchmark_data.py`); per-item detail in JSONB. New benchmark = code change in `benchmarks/`, not a schema migration.

**`benchmark_runs`:**

| Column | Type (sketch) | Example |
|--------|---------------|---------|
| `id` | UUID | |
| `model_id` | FK → `models` | |
| `gateway_model_id` | string | `gpt-4.1-mini` |
| `benchmark_key` | string | `ifeval` \| `truthfulqa` \| `mmlu` \| `tomi` \| `consistency` |
| `inference_backend` | string | `gateway` (default) \| `dcc` — column in DDL; DCC pillar wiring planned |
| `status` | string | `complete` |
| `headline_metric` | string | `pass_rate` \| `accuracy` \| `mean_f1` |
| `headline_value` | float | `0.83` |
| `n_items` | int | `120` |
| `metrics` | JSONB | benchmark summary, e.g. MMLU `per_subject` |
| `items` | JSONB | per-item rows for drill-down |
| `run_params` | JSONB, nullable | e.g. `{"mmlu_sample": 200}` |
| `started_at` / `completed_at` | timestamptz | |

If a benchmark needs SQL filtering over items, promote to child `benchmark_items` (`run_id`, `idx`, `passed`, `score`, `payload` JSONB) — envelope unchanged.

---

## `deployment_context`

How the model is offered (ITSO). Stored on `models` and/or copied onto `safety_runs`.

```json
{
  "deployment_type": "chatbot",
  "has_tools": false,
  "has_guardrails": true,
  "data_access": "none",
  "commercial_vs_oss": "commercial"
}
```

---

## Nutrition label aggregate (`GET /models/{id}`)

Example shape:

```json
{
  "gateway_model_id": "gpt-4.1-mini",
  "display_name": "GPT 4.1 Mini",
  "deployment_context": { "deployment_type": "chatbot" },
  "scanning": { "latest_severity": null, "note": "N/A for cloud-only gateway" },
  "safety": { "latest_run_id": "…", "pass_rate": 0.85, "categories": [] },
  "efficacy": [
    { "suite_key": "it_support", "score": 0.78, "run_at": "2026-05-28T12:00:00Z" }
  ],
  "benchmarks": [
    { "benchmark_key": "ifeval", "headline_metric": "pass_rate", "headline_value": 0.83, "n_items": 120 }
  ]
}
```

Exact nesting is owned by `api/` + `frontend/`; table shapes above are the source of truth.
