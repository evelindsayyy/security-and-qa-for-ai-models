# Garak output

Gitignored except this README.

| File | Step |
|------|------|
| `garak-gpt41mini-low-guardrail.report.jsonl` | 1 — raw scan |
| `garak-gpt41mini-low-guardrail.report.html` | 1 — HTML report |
| `safety_result.json` | 2 — `SafetyRunResult` export |
| `.garak-*` | cache / logs |

Config: `../garak_gpt41mini_low_guardrail.yaml`. Probes in export: `safety_result.json` → `tool_results.garak.probe_ids`.
