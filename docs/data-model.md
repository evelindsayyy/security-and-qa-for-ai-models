# Data model (Postgres sketch)

**Scope:** tables, columns, JSON field shapes. **Not here:** component diagrams or API flows — see [`architecture.md`](architecture.md).

Shared reference for **Team** schema work and Track A/B structured outputs. Implementation: week 5 API; design starts week 2.

Related: [`gateway-models.md`](gateway-models.md).

---

## Design principles

- One **`models`** row per gateway model (and optionally per HF repo for on-prem).
- **Scanning** results link to `hf_repo` / scan jobs.
- **Safety** and **efficacy** results link to `gateway_model_id` + `deployment_context`.
- Store **raw tool JSON** paths or JSONB blobs for audit; dashboard reads normalized fields.

---

## Entity relationship (target)

GitLab and GitHub render the flowchart below. (Entity-relationship diagrams with column lists often fail in GitLab’s Mermaid parser; use the [table reference](#table-reference-postgresql) for exact columns.)

```mermaid
flowchart TB
  subgraph catalog [Catalog]
    models[(models)]
    task_suites[(task_suites)]
  end

  subgraph security_scanning [Security - scanning]
    scans[(scans)]
    findings[(findings)]
  end

  subgraph security_safety [Security - safety]
    safety_runs[(safety_runs)]
    safety_findings[(safety_findings)]
  end

  subgraph efficacy [Efficacy]
    eval_runs[(eval_runs)]
    eval_results[(eval_results)]
  end

  models --> scans
  scans --> findings
  models --> safety_runs
  safety_runs --> safety_findings
  task_suites --> eval_runs
  eval_runs --> eval_results
  models --> eval_results
```

### Table reference (PostgreSQL)

| Table | Primary key | Foreign keys | Main columns |
|-------|-------------|--------------|--------------|
| `models` | `id` | — | `gateway_model_id`, `hf_repo` (optional), `display_name`, `provider`, `deployment_type`, `deployment_context` (JSONB) |
| `scans` | `id` (uuid) | `model_id` → `models` | `status`, `risk_score`, `risk_level`, `scan_result_json`, `finished_at` |
| `findings` | `id` (uuid) | `scan_id` → `scans` | `source`, `category`, `severity`, `detail` |
| `safety_runs` | `id` (uuid) | `model_id` → `models` | `status`, `deployment_context`, `tool_results`, `finished_at` |
| `safety_findings` | `id` (uuid) | `safety_run_id` → `safety_runs` | `category`, `probe_source`, `passed`, `detail` |
| `task_suites` | `id` | — | suite metadata (name, version) |
| `eval_runs` | `id` (uuid) | `task_suite_id` → `task_suites` | `status`, `finished_at` |
| `eval_results` | `id` (uuid) | `eval_run_id`, `model_id` | `task_id`, `score`, `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd` (optional) |

---

## Structured outputs (by track)

| Track | Job | Python type (spike) | DB home |
|-------|-----|---------------------|---------|
| A — scanning | HF artifact scan | `ScanResult`, `Finding` | `scans`, `findings` |
| A — safety | Red team run | `SafetyResult` (W2+) | `safety_runs`, `safety_findings` |
| B — efficacy | Task suite run | `EvalRun`, `TaskResult` (Track B) | `eval_runs`, `eval_results` |

Spike files today:

| Track | File |
|-------|------|
| A — scanning | `testing/scanning/schemas.py`, `output/<model>/combined_scan.json` |
| B — efficacy | `testing/eval/truthfulqa/` CSV columns below (W2); Pydantic TBD W3 |

### TruthfulQA spike → `eval_results` (W2)

Detail CSV columns map to future `eval_results` rows:

| CSV column | DB field (target) |
|------------|-------------------|
| `provider_name` | logical provider alias |
| `model` | `gateway_model_id` |
| `row_index` | `task_id` or external id |
| `correct` | `score` (0/1) |
| `gold_letter`, `pred_letter` | store in `detail` JSONB |

Summary CSV: `provider_name`, `model`, `n`, `accuracy` → aggregate on `eval_runs`.

Committed sample: `testing/eval/output/samples/truthfulqa_w2_summary.csv`.

---

## `deployment_context` (JSON)

Agreed in week 2 Team issue. Suggested fields:

```json
{
  "surface": "chatbot | agentic",
  "guardrails_enabled": true,
  "tools_connected": false,
  "commercial_vs_oss": "commercial | oss",
  "notes": ""
}
```

Safety probe subsets and efficacy task subsets may differ for the same model — document in issue comments, not a single shared probe list.

---

## Nutrition label API (week 5)

`GET /models/{id}` returns summary:

```json
{
  "model_id": "...",
  "security": {
    "scanning": { "risk_level": "low", "last_scan_at": "..." },
    "safety": { "categories": [{ "name": "jailbreak", "passed": false }] }
  },
  "efficacy": { "suites": [{ "name": "it_support", "score": 0.82 }] }
}
```

Track A owns `security.*`; Track B owns `efficacy`; Team owns aggregation endpoint.
