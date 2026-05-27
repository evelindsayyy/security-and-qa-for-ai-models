# scanner output format (draft)

> documents what pillar 1 security scans should produce.
> the test in `testing/security_scanning_tests/` generates a first version of this shape.

---

## target schema (future `ScanResult`)

our scanner should eventually output something like:

```json
{
  "model_id": "distilbert-base-uncased",
  "scanned_files": ["pytorch_model.bin", "model.safetensors"],
  "overall_risk_score": 0,
  "severity_tier": "low",
  "findings": [],
  "tool_results": {
    "modelscan": { },
    "fickling": { }
  },
  "scan_metadata": {
    "scanned_at": "2026-05-26T19:50:00+00:00",
    "scanner_version": "scanner_spike-0.1.0",
    "container_image": "testing/scanner_spike"
  }
}
```

| field | meaning |
|---|---|
| `overall_risk_score` | 0–100 weighted score (placeholder `0` in spike) |
| `severity_tier` | `low` / `medium` / `high` / `critical` |
| `findings` | list of individual issues (from modelscan `issues[]`) |
| `tool_results` | raw-ish output from each tool for audit trail |

---

## modelscan output

modelscan writes json with roughly:

```json
{
  "summary": {
    "total_issues_by_severity": {
      "CRITICAL": 0,
      "HIGH": 0,
      "MEDIUM": 0,
      "LOW": 0
    },
    "total_issues": 0,
    "input_path": "/models/distilbert-base-uncased"
  },
  "issues": [],
  "errors": []
}
```

each item in `issues` (when present) may include:

- `description` — human-readable finding
- `operator` — pickle op that triggered it (e.g. `REDUCE`)
- `module` — python module referenced
- `severity` — `{ "name": "CRITICAL", "value": 1 }`
- `source` — file path inside the model dir

spike script: `run_modelscan.py` → `output/modelscan_report.json`

---

## fickling output

fickling analyzes pickle serialization in `.bin` files. spike captures:

```json
{
  "file": "/models/distilbert-base-uncased/pytorch_model.bin",
  "is_likely_safe": true,
  "ast_node_count": 1234,
  "ast_node_types": {
    "Global": 50,
    "Put": 100
  }
}
```

| field | meaning |
|---|---|
| `is_likely_safe` | fickling's high-level safety signal |
| `ast_node_count` | nodes in the pickle AST |
| `ast_node_types` | breakdown of node types (for debugging / docs) |

spike script: `run_fickling.py` → `output/fickling_report.json`

---

## combined report

`run_combined_scan.py` merges both into `output/combined_scan.json`.
copy one run to `testing/fixtures/sample_scan_result.distilbert.json` for the team.

---

## severity mapping (spike logic)

| modelscan counts | `severity_tier` |
|---|---|
| any CRITICAL | `critical` |
| any HIGH | `high` |
| any MEDIUM | `medium` |
| otherwise | `low` |

real `overall_risk_score` weighting lives in `scanner/` later (see `docs/architecture.md`).
