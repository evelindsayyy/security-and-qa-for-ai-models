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

```mermaid
erDiagram
  MODEL ||--o{ SCAN : has
  MODEL ||--o{ SAFETY_RUN : has
  MODEL ||--o{ EVAL_RUN : has
  SCAN ||--o{ FINDING : produces
  SAFETY_RUN ||--o{ SAFETY_FINDING : produces
  EVAL_RUN ||--o{ EVAL_RESULT : contains
  TASK_SUITE ||--o{ EVAL_RUN : drives

  MODEL {
    string id PK
    string gateway_model_id
    string hf_repo nullable
    string display_name
    string provider
    string deployment_type
    json deployment_context
    timestamp first_seen
  }
  SCAN {
    uuid id PK
    string model_id FK
    string status
    int risk_score
    string risk_level
    json scan_result_json
    timestamp finished_at
  }
  FINDING {
    uuid id PK
    uuid scan_id FK
    string source
    string category
    string severity
    text detail
  }
  SAFETY_RUN {
    uuid id PK
    string model_id FK
    string status
    json deployment_context
    json tool_results
    timestamp finished_at
  }
  SAFETY_FINDING {
    uuid id PK
    uuid safety_run_id FK
    string category
    string probe_source
    bool passed
    text detail
  }
  EVAL_RUN {
    uuid id PK
    string task_suite_id FK
    string status
    timestamp finished_at
  }
  EVAL_RESULT {
    uuid id PK
    uuid eval_run_id FK
    string model_id FK
    string task_id
    float score
    int latency_ms
    int tokens_in
    int tokens_out
    float cost_usd nullable
  }
```

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
