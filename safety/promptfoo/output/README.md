# Promptfoo output

Gitignored except this README.

| File | Step |
|------|------|
| `eval.json` | 1 — raw policy eval |
| `redteam_eval.json` | 2 — raw red-team eval |
| `safety_result.json` | 1b — policy `SafetyRunResult` export |
| `redteam_safety_result.json` | 2b — red-team `SafetyRunResult` export |
| `.promptfoo/` | web UI database |

Configs: `../promptfooconfig.yaml`, `../promptfooconfig.redteam.yaml`. Probes: `safety_result.json` → `tool_results.promptfoo.probe_ids`.
