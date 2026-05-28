# GPT-2 scan calibration

Track A (security). First DGX scan used to tune the risk scorer.

| Field | Value |
|-------|-------|
| Model | `gpt2` (known-safe, legacy PyTorch `.bin`) |
| Date | 2026-05-27 |
| Tools | ModelScan 0.8.8, Fickling |

## Results

| Signal | Value |
|--------|-------|
| ModelScan issues | 0 (all severities) |
| Files scanned | `pytorch_model.bin`, pickles in `rust_model.ot` |
| Files skipped | 212 |
| Fickling | LIKELY_UNSAFE |
| Format | `pytorch_stacked_pickle`, stack_count 5, 336 AST nodes |

## Implications

1. Merge ModelScan and Fickling into a single `ScanResult`; do not block on Fickling alone.
2. Document why ModelScan skips files (coverage gap).
3. Week 3: risk scoring formula with explicit disagreement handling.

Artifact: `testing/security_scanning_tests/output/gpt2/combined_scan.json` (local, gitignored).
