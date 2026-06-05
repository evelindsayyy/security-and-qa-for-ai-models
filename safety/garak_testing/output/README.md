# Garak Output

Generated Garak artifacts. Everything here except this README is **gitignored**.

## Expected files (after a scan)

| File / directory | Use |
|------------------|-----|
| `garak-gpt41mini-low-guardrail.report.jsonl` | Raw per-attempt log — feed to `export_safety_result.py` |
| `garak-gpt41mini-low-guardrail.report.html` | Interactive HTML report (open in browser) |
| `safety_result.json` | `SafetyResult`-shaped export (`docs/data-model.md`) |
| `.garak-data/` | Garak logs (`garak.log`) |
| `.garak-cache/` | Detector model cache (torch, HF datasets) |
| `.garak-home/` | Container HOME for ML libs |
| `.garak-config/` | Optional site config |

## Viewing results

1. **Quick pass/fail:** `safety_result.json` or the HTML report.
2. **Live progress:** `tail -f .garak-data/garak/garak.log`

Do not commit generated outputs unless a small reviewed sample is intentionally needed.
