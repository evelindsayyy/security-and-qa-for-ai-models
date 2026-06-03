# Scanner (`scanner/`)

Track A — HF artifact scanning: **ModelScan** + **Fickling** + **ModelAudit** → **risk scorer** → `scan_result.json` (Postgres-ready per [`docs/data-model.md`](../docs/data-model.md)).

## Pipeline

```text
download → format_detector
         → ModelScan (whole repo; extension-routed)
         → Fickling (every pickle-family weight file)
         → ModelAudit (all candidate files; content-routed inside ModelAudit)
         → risk_scorer (deduped findings) → scan_result.json
```

| Tool | Role |
|------|------|
| **ModelScan** | Pickle / H5 / SavedModel paths; may skip `.bin`/`.pt` by extension |
| **Fickling** | Pickle AST on each pickle-family file (`per_file` in `tool_results`) |
| **ModelAudit** | Magic-byte routing across 45+ formats; overlaps ModelScan/Fickling by design |
| **Risk scorer** | Max severity across tools; dedupes `(file, signal)`; `corroborated_by` when tools agree |

Defense-in-depth: the same payload may be reported by more than one tool. Correlated findings merge into one row.

## Risk scorer

| Input | Effect on label |
|-------|-----------------|
| ModelScan HIGH/CRITICAL | Raises tier/score |
| Fickling LIKELY_UNSAFE, ModelScan clean | Stays **low**, score ~18 (benign PyTorch pickles) |
| Fickling LIKELY_OVERTLY_MALICIOUS | **high** tier signal |
| ModelAudit actionable (medium+) | Raises tier; install-missing warnings filtered |
| `safetensors_only` | Fickling omitted from label |

**Calibration**

| Model | Tier / score | Notes |
|-------|----------------|-------|
| gpt2, distilbert, BAAI/bge-small-en-v1.5 | low / 18 | Benign stacked pickle; ModelAudit warnings filtered |
| neimasilk/modelscan-extension-mismatch-poc | critical / 95 | ModelScan 0 issues; Fickling + ModelAudit flag disguised pickles |

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
| `metadata` | Hub file list only |
| `modelscan` | Debug: ModelScan only |
| `fickling` | Debug: Fickling only |
| `modelaudit` | Debug: ModelAudit only (content-routed) |

## Layout

| Path | Role |
|------|------|
| `scanner/*.py` | Production |
| `experiments/` | OSV, Trivy spikes |
| `unit_tests/` | Host unit tests |
| `models/`, `output/` | DGX data (gitignored) |

## Source file map (for newcomers)

| Module | Responsibility |
|--------|----------------|
| `__main__.py` | CLI: `scan`, `metadata`, debug subcommands, `validate` |
| `pipeline.py` | Orchestrates download → tools → `scan_result.json` |
| `download.py` | `snapshot_download` into `models/<slug>/` |
| `metadata.py` | Hub file list without weights |
| `format_detector.py` | File categories + `safetensors_only` / Fickling flags |
| `pickle_scan.py` | ModelScan whole-repo + Fickling per pickle-family file |
| `modelaudit_scan.py` | Content-routed ModelAudit + noise filtering |
| `risk_scorer.py` | Merge tools → tier, score, deduped `findings[]` |
| `schemas.py` | Pydantic `ScanResult` / `Finding` (Postgres-ready) |
| `paths.py` | `MODELS_ROOT`, `OUTPUT_ROOT`, slug helpers |
| `report_text.py` | Terminal summaries for debug commands |
