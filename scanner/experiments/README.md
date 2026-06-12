# Scanner experiments

Optional spikes. Production: `python -m scanner scan` (ModelScan + Fickling + ModelAudit + pip-audit/OSV + TruffleHog).

| Script | Purpose |
|--------|---------|
| `compare_osv_pip_audit.py` | Early spike — logic now in `scanner/dependency_scan.py` |
| `run_trivy.py` | Trivy FS (`compose.trivy.yml`) |

Debug partial runs (same as pipeline tools):

- `python -m scanner modelaudit <HF_REPO_ID>`
- `python -m scanner deps <HF_REPO_ID>`
- `python -m scanner secrets <HF_REPO_ID>`
