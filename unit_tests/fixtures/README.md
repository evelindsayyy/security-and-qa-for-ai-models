# Fixtures (committed)

Small JSON samples for unit tests. **Not** live runtime output (those dirs are gitignored).

| File | Used by |
|------|---------|
| `gpt2_combined_scan.json` | `test_risk_scorer.py` |
| `garak_sample.report.jsonl` | `test_garak_exporter.py` |
| `promptfoo_gpt41mini_safety_result.json` | `test_safety_scorer.py` |
| `garak_gpt41mini_safety_result.json` | `test_safety_scorer.py` |
| `promptfoo_gpt41mini_redteam_eval.json` | `test_safety_scorer.py` (trimmed Promptfoo eval) |
