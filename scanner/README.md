# Scanner (`scanner/`)

Track A — HF artifact scanning: **ModelScan** + **Fickling** + **ModelAudit** → **risk scorer** → `scan_result.json` (Postgres-ready per [`docs/data-model.md`](../docs/data-model.md)).

## Pipeline

```text
download → format_detector
         → ModelScan (pickle/H5/SavedModel; whole repo)
         → Fickling (pytorch_model.bin if present)
         → ModelAudit (safetensors + .onnx only — fills ModelScan gaps)
         → risk_scorer → scan_result.json + findings[]
```

| Tool | Scope | In `tool_results` |
|------|--------|-------------------|
| ModelScan | Repo; skips safetensors/onnx | `modelscan` + `modelscan_report.json` |
| Fickling | Legacy pickle weights | `fickling` |
| ModelAudit | `format_detector` safetensors/onnx paths | `modelaudit` |
| Risk scorer | Single tier + score | top-level + `findings[]` (`source` per tool) |

## Risk scorer

| Input | Effect on label |
|-------|-----------------|
| ModelScan HIGH/CRITICAL | Raises tier/score; `source: modelscan` findings |
| Fickling on `.bin`, ModelScan clean | Stays **low**, score ~18; one low fickling finding |
| ModelAudit on safetensors/onnx | Only **actionable** issues (medium+); pickle-bin noise filtered |
| `safetensors_only` | Fickling skipped |

gpt2 baseline: **low / 18**, ModelScan 0 issues, ModelAudit 0 on `model.safetensors`, one fickling finding.

## DGX/VM setup

```bash
cd scanner/docker
cp .env.example .env
sed -i "s/^UID=.*/UID=$(id -u)/" .env && sed -i "s/^GID=.*/GID=$(id -g)/" .env
docker compose build
docker compose run --rm scanner python -m scanner scan gpt2
docker compose run --rm scanner python -m scanner validate gpt2
```

Outputs: `scanner/output/<slug>/scan_result.json` (primary), `combined_scan.json`, `modelscan_report.json`, `modelaudit_report.json` when applicable.

## New models

```bash
docker compose run --rm scanner python -m scanner scan <HF_REPO_ID>
```

Hub `org/model` → `models/org--model/`, `output/org--model/scan_result.json`. Set `HF_TOKEN` in `.env` for gated models.

## CLI

| Command | Purpose |
|---------|---------|
| `scan` | Full pipeline → `scan_result.json` |
| `validate` | Check existing JSON |
| `gap-map` | ModelScan coverage table |
| `metadata` | Hub file list only |
| `modelscan` | Debug: ModelScan only |
| `fickling` | Debug: Fickling only |
| `modelaudit` | Debug: ModelAudit only (safetensors/onnx) |

## Layout

| Path | Role |
|------|------|
| `scanner/*.py` | Production |
| `experiments/` | OSV, Trivy spikes |
| `unit_tests/` | Host unit tests |
| `models/`, `output/` | DGX data (gitignored) |
