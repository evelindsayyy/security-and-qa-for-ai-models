# scanner output format (draft)

what pillar 1 security scans should produce.
`testing/security_scanning_tests/` is a spike — not the final production schema.

---

## spike vs production

| spike (now) | production `scanner/` (later) |
|---|---|
| `severity_tier` from modelscan only | weighted merge of modelscan + fickling + other checks |
| `overall_risk_score: 0` placeholder | 0–100 rubric in `docs/architecture.md` |
| full modelscan raw output in separate json | combined report trimmed; full audit trail in db |
| fickling txt note about false positives | remediation notes per finding |

---

## combined report shape

```json
{
  "model_id": "distilbert-base-uncased",
  "scanned_files": ["pytorch_model.bin", "rust_model.ot:model/data.pkl"],
  "overall_risk_score": 0,
  "severity_tier": "low",
  "fickling_severity": "LIKELY_UNSAFE",
  "findings": [],
  "tool_results": {
    "modelscan": {
      "total_issues": 0,
      "scanned_files": ["pytorch_model.bin"],
      "total_skipped": 129
    },
    "fickling": {
      "pytorch_format": "pytorch_stacked_pickle",
      "is_likely_safe": false,
      "severity": "LIKELY_UNSAFE"
    }
  }
}
```

---

## reading distilbert results (expected)

**modelscan — clean**
- 0 issues, `severity_tier: low`
- scanned `pytorch_model.bin` and pickles inside `rust_model.ot`
- skipped 129 files (tensor weights, vocab, config, safetensors, hf cache) — normal

**fickling — often flags benign pytorch**
- `pytorch_stacked_pickle`, `stack_count: 5` — distilbert legacy format
- `LIKELY_UNSAFE` / `is_likely_safe: false` is common on legit pytorch weight pickles
- fickling is stricter about pickle opcodes; does not mean the model is malicious
- production scanner must merge both signals, not treat fickling alone as a block

**contradiction is intentional for now**
- `severity_tier: low` (modelscan) + `fickling_severity: LIKELY_UNSAFE` shows why we need a real risk scorer

---

## output files

| file | contents |
|---|---|
| `modelscan_report.json` | full modelscan api output including skipped list |
| `modelscan_report.txt` | short human summary |
| `fickling_report.json` | fickling analysis of pytorch_model.bin |
| `fickling_report.txt` | short human summary + false positive note |
| `combined_scan.json` | merged dashboard-style report (trimmed) |
