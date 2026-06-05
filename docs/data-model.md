# Data model

Target **PostgreSQL** schema for week 5 [`api/`](../api/README.md) (see [`architecture.md`](architecture.md)). Weeks 3–4: each package writes **JSON** with the same logical shapes (validated in code); Postgres comes later.

Catalog keys: [`gateway-models.md`](gateway-models.md).

---

## Principles

- One **`models`** row per gateway model (`gateway_model_id`; optional `hf_repo` when weights are on-prem).
- **Scanning:** `models` → `scans` → `findings` (HF artifact jobs only).
- **Safety:** `models` → `safety_runs` → `safety_findings` (gateway inference).
- **Efficacy:** `task_suites` → `eval_runs` → `eval_results` (each result links to one `models` row).
- **UI reads normalized fields;** investigators can drill into `tool_results` or `detail` JSONB.

```text
models ──┬── scans ── findings
         ├── safety_runs ── safety_findings
         └── eval_runs ── eval_results
task_suites ── eval_runs
```

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
| `tool_results` | JSONB | `{"modelscan": {...}, "fickling": {...}, "modelaudit": {...}}` |
| `scan_metadata` | JSONB | `{"duration_s": 120, "worker": "dgx-01"}` |
| `started_at` / `completed_at` | timestamptz | |

**`findings`** (child rows — one issue per actionable item):

| Column | Example |
|--------|---------|
| `id` | UUID |
| `scan_id` | FK |
| `source` | `modelscan` \| `fickling` \| `modelaudit` \| `pip_audit` \| `trufflehog` |
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

One red-team job against one or more gateway models.

**`safety_runs`:**

| Column | Example |
|--------|---------|
| `id` | UUID |
| `gateway_model_id` | `gpt-4.1-mini` |
| `status` | `complete` |
| `deployment_context` | JSONB (required for ITSO-aligned probes) |
| `probe_suite` | string | `garak_subset_v1` or `promptfoo_duke_policy_v1` |
| `summary_pass_rate` | float | `0.85` |
| `tool_results` | JSONB | `{"garak": {...}, "promptfoo": {...}}` — **format TBD after W3 runs** |
| `started_at` / `completed_at` | timestamptz | |

**`safety_findings`** (normalized for UI):

| Column | Example |
|--------|---------|
| `id` | UUID |
| `safety_run_id` | FK |
| `category` | `jailbreak` \| `toxicity` \| `policy` \| `leakage` |
| `source` | `garak` \| `promptfoo` \| `duke_probe` |
| `passed` | bool | `false` |
| `severity` | `medium` |
| `title` | `academic integrity — graded submission request` |
| `description` | text |
| `probe_id` | string | `duke.policy.003` |

Week 3 work: run garak and promptfoo, save sample JSON, then lock Pydantic types in `safety/schemas.py` to match this table.

---

## `task_suites` / `eval_runs` / `eval_results` (Track B — efficacy)

**`task_suites`:**

| Column | Example |
|--------|---------|
| `id` | UUID |
| `suite_key` | `it_support` \| `policy_qa` \| `summarization` |
| `version` | `1.0` |
| `yaml_path` | `tasks/rubrics/it_support.yaml` |

**`eval_runs`:**

| Column | Example |
|--------|---------|
| `id` | UUID |
| `suite_id` | FK → `task_suites` |
| `gateway_model_id` | `gpt-4.1-mini` |
| `status` | `complete` |
| `aggregate_score` | float | `0.78` (suite-defined) |
| `latency_p50_ms` | int | `1200` |
| `tokens_in_total` / `tokens_out_total` | int | |
| `cost_usd_total` | decimal, nullable | |
| `tool_results` | JSONB | optional raw judge logs |
| `started_at` / `completed_at` | timestamptz | |

**`eval_results`** (per task / prompt):

| Column | Example |
|--------|---------|
| `id` | UUID |
| `eval_run_id` | FK |
| `model_id` | FK → `models` |
| `task_id` | string | `it_support_014` |
| `score` | float | `1.0` or rubric 0–5 |
| `metric` | string | `accuracy` \| `rouge_l` \| `judge_score` |
| `latency_ms` | int | `890` |
| `tokens_in` / `tokens_out` | int | |
| `cost_usd` | decimal, nullable | |
| `detail` | JSONB | `{"judge_reason": "...", "reference": "..."}` |

TruthfulQA W2 columns (`provider_name`, `accuracy`) fold into this shape when we promote benchmark runs to `evaluator/`.

---

## `deployment_context`

Describes how the model is offered so probes and tasks match reality (ITSO). Stored on `models` and/or copied onto `safety_runs` (and optionally eval runs).

Example (fields still being agreed in a Team W3 issue):

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

Week 5 API returns one JSON document per model, for example:

```json
{
  "gateway_model_id": "gpt-4.1-mini",
  "display_name": "GPT 4.1 Mini",
  "deployment_context": { "deployment_type": "chatbot" },
  "scanning": { "latest_severity": null, "note": "N/A for cloud-only gateway" },
  "safety": { "latest_run_id": "…", "pass_rate": 0.85, "categories": [] },
  "efficacy": [
    { "suite_key": "it_support", "score": 0.78, "run_at": "2026-05-28T12:00:00Z" }
  ]
}
```

Exact nesting is owned by `api/` + `frontend/` in week 5–6; table shapes above are the source of truth.

---
