# Scanning spike (Track A)

Dockerized HF artifact scanning on DGX — ModelScan, Fickling, deps, optional Trivy. **Purpose:** run tools, inspect raw output, map to [`docs/data-model.md`](../../docs/data-model.md) (`scans`, `findings`). Spike schemas: `schemas.py`. Production: [`scanner/`](../../scanner/).

---

## Quick start (DGX)

**One-time:** run as your user (not root).

```bash
cd ~/security-and-qa-for-ai-models/testing/scanning
cp .env.example .env
sed -i "s/^UID=.*/UID=$(id -u)/" .env
sed -i "s/^GID=.*/GID=$(id -g)/" .env
mkdir -p models output
docker compose -f docker/compose.yml build
docker compose -f docker/compose.yml run --rm scanner bash
```

Inside container:

```bash
python download_model.py
python run_modelscan.py
python run_fickling.py
python run_combined_scan.py
ls /output/$MODEL_ID/
```

After every `git pull`: rebuild the image.

---

## Script index

| Script | Purpose | Output |
|--------|---------|--------|
| `download_model.py` | HF weights to `/models/` | `models/<slug>/` |
| `run_modelscan.py` | Pickle/format scan | `output/<id>/modelscan_report.*` |
| `run_fickling.py` | Pickle AST on `.bin` | `output/<id>/fickling_report.*` |
| `run_combined_scan.py` | Merge → `ScanResult` | `output/<id>/combined_scan.json` |
| `list_model_metadata.py` | HF API only (no download) | `output/<id>/metadata.json` |
| `compare_osv_pip_audit.py` | OSV vs pip-audit spike | `output/osv_pip_audit_spike/` |
| `schemas_demo.py` | Validate `ScanResult` | stdout |
| `run_trivy.py` | FS vuln scan (Nithi spike) | `output/<id>/trivy_report.*` |

Schemas: `schemas.py` (`ScanRequest`, `ScanResult`, `Finding`).

---

## Trivy (Nithi)

Separate image with Trivy installed. Production scanning standardized on pip-audit + OSV (see [`docs/tool-stack.md`](../../docs/tool-stack.md)).

```bash
docker compose -f docker/compose.trivy.yml build
docker compose -f docker/compose.trivy.yml run --rm scanner-trivy bash
python download_model.py   # if needed
python run_trivy.py
```

---

## Models to test

Set `MODEL_ID` in `.env`. On disk, `org/model` → `org--model` under `models/`.

| Tier | MODEL_ID | Notes |
|------|----------|-------|
| 1 | `distilbert-base-uncased` | Default regression |
| 1 | `gpt2` | Calibration baseline |
| 1 | `facebook/opt-125m` | Org path |
| 1 | `bert-base-uncased`, `sentence-transformers/all-MiniLM-L6-v2` | Fast reruns |
| 2 | `TinyLlama/TinyLlama-1.1B-Chat-v1.0`, `microsoft/phi-2` | More disk/time |
| 2 | `google/gemma-2-2b` | Needs `HF_TOKEN` + license |

Skip 7B+ on shared DGX unless required.

| Format | ModelScan | Fickling |
|--------|-----------|----------|
| `pytorch_model.bin` | yes | yes |
| `model.safetensors` | often skipped | n/a |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Permission denied on `models/` or `output/` | Set UID/GID in `.env`; chown via `docker run --rm -v "${PWD}/models:/work" ubuntu chown -R $(id -u):$(id -g) /work` |
| Stale distilbert after pull | `docker compose -f docker/compose.yml build` |
| `python` not found on host | Run only inside container |
| Fickling errors on safetensors-only repos | Expected |

Do not run spike Python on the DGX host — dependencies are in the container only.
