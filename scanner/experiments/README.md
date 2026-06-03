# Scanner experiments

Optional spikes. Production: `python -m scanner scan` (ModelScan + Fickling + ModelAudit).

| Script | Purpose |
|--------|---------|
| `compare_osv_pip_audit.py` | OSV vs pip-audit |
| `run_trivy.py` | Trivy FS (`compose.trivy.yml`) |

Debug ModelAudit (same as pipeline): `python -m scanner modelaudit <HF_REPO_ID>`
