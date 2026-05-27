# scanner output format (draft)

documents what pillar 1 security scans should produce.
`testing/security_scanning_tests/` generates a first version of this shape.

---

## target schema (future `ScanResult`)

```json
{
  "model_id": "distilbert-base-uncased",
  "scanned_files": ["pytorch_model.bin", "model.safetensors"],
  "overall_risk_score": 0,
  "severity_tier": "low",
  "findings": [],
  "tool_results": {
    "modelscan": {},
    "fickling": {}
  },
  "scan_metadata": {
    "scanned_at": "2026-05-26T19:50:00+00:00",
    "scanner_version": "security_scanning_tests-0.1.0"
  }
}
```

| field | meaning |
|---|---|
| `overall_risk_score` | 0–100 weighted score (placeholder `0` for now) |
| `severity_tier` | `low` / `medium` / `high` / `critical` |
| `findings` | modelscan `issues[]` |
| `tool_results` | raw tool output for audit trail |

---

## modelscan

api returns `summary`, `issues`, `errors`. see `output/modelscan_report.json`.

severity tier mapping:

| modelscan counts | `severity_tier` |
|---|---|
| any CRITICAL | `critical` |
| any HIGH | `high` |
| any MEDIUM | `medium` |
| otherwise | `low` |

---

## fickling

`pytorch_model.bin` may be a zip (modern) or stacked pickle (distilbert).

```json
{
  "file": "/models/distilbert-base-uncased/pytorch_model.bin",
  "pytorch_format": "pytorch_stacked_pickle",
  "stack_count": 2,
  "is_likely_safe": true,
  "severity": "LIKELY_SAFE",
  "ast_node_count": 1234
}
```

| field | meaning |
|---|---|
| `pytorch_format` | `pytorch_zip`, `pytorch_stacked_pickle`, or `raw_pickle` |
| `is_likely_safe` | all stacked pickles passed fickling checks |
| `severity` | worst severity across stacked pickles |
| `ast_node_count` | total ast nodes across all pickles in the file |
