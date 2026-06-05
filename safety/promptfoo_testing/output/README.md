# Promptfoo Output (smoke spike)

Gitignored except this README. Filenames use **`smoke_`** to distinguish from scanner `scan_result.json` and other production artifacts.

| File | Step |
|------|------|
| `smoke_eval.json` | 1 — raw smoke eval |
| `smoke_safety_result.json` | 1b — normalized (`export_safety_result.py`) |
| `smoke_redteam_eval.json` | 2 — raw red-team eval |
| `.promptfoo/` | 1 or 2 — web UI database |
| `logs/` | runtime logs |

Input configs: `../promptfooconfig.yaml`, `../promptfooconfig.redteam.yaml`.

Legacy names (`smoke.json`, `redteam.json`, `safety_result.json`, `redteam.yaml`) are old runs — safe to delete.
