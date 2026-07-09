# Scanner (`scanner/`)

Track A — HF artifact scanning: **ModelScan** + **Fickling** + **ModelAudit** + **pip-audit/OSV** + **TruffleHog** → **risk scorer** → `scan_result.json` (Postgres-ready per [`docs/data-model.md`](../docs/data-model.md)).

Scans can be launched and viewed from the **frontend** (`/scans` → "Start a new scan"); see [`frontend/README.md`](../frontend/README.md). The CLI below is the same pipeline.

## Pipeline

```text
download → format_detector
         → ModelScan (whole repo; extension-routed)
         → Fickling (every pickle-family weight file)
         → ModelAudit (all candidate files; content-routed inside ModelAudit)
         → pip-audit + OSV (dependency manifests)
         → TruffleHog (filesystem secrets)
         → risk_scorer (deduped findings) → scan_result.json
```

| Tool | Role |
|------|------|
| **ModelScan** | Pickle / H5 / SavedModel paths; may skip `.bin`/`.pt` by extension |
| **Fickling** | Pickle AST on each pickle-family file (`per_file` in `tool_results`) |
| **ModelAudit** | Magic-byte routing across 45+ formats; overlaps ModelScan/Fickling by design |
| **pip-audit + OSV** | Python CVEs via requirements; OSV corroborates and covers other manifests |
| **TruffleHog** | Leaked credentials/secrets in repo files (redacted in output) |
| **Risk scorer** | Max severity across tools; dedupes `(file, signal)`; `corroborated_by` when tools agree |

Defense-in-depth: the same payload may be reported by more than one tool. Correlated findings merge into one row.

## Risk scorer

| Input | Effect on label |
|-------|-----------------|
| ModelScan HIGH/CRITICAL | Raises tier/score |
| Fickling LIKELY_UNSAFE, ModelScan clean | Stays **low**, score ~18 (benign PyTorch pickles) |
| Clean scan (no findings) | **low**, score **0** |
| Fickling LIKELY_OVERTLY_MALICIOUS | **high** tier signal |
| ModelAudit actionable (medium+) | Raises tier; install-missing warnings filtered |
| pip-audit/OSV HIGH/CRITICAL CVE | Raises tier |
| TruffleHog verified secret | **critical** tier |
| TruffleHog unverified secret | **high** tier |
| `safetensors_only` | Fickling omitted from label |

**Calibration** (sample)

| Model | Tier / score | Notes |
|-------|----------------|-------|
| gpt2, distilbert, BAAI/bge-small-en-v1.5 | low / 18 | Benign stacked pickle; ModelAudit warnings filtered |
| safetensors-only, no findings | low / 0 | Clean artifact |
| neimasilk/modelscan-extension-mismatch-poc | critical / 95 | ModelScan 0 issues; Fickling + ModelAudit flag disguised pickles |
| scan-test/supply-chain-demo | medium / 40 | Local fixture: `requirements.txt` (pip-audit + OSV); optional secret patterns in `credentials.env` |

## Run

Production scans run on the **application VM** via the UI or CLI. Secrets (`HF_TOKEN`, optional) come from the repo-root `.env`. Shared Docker patterns: [`docs/cli.md`](../docs/cli.md).

```bash
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env -f scanner/docker/compose.yml run --rm scanner \
  python -m scanner scan gpt2
```

Build once: `docker compose --env-file .env -f scanner/docker/compose.yml build`.

Outputs: `scanner/output/<slug>/scan_result.json` (primary), `combined_scan.json`, `modelscan_report.json`, `modelaudit_report.json` when applicable.

## New models

```bash
env UID=$(id -u) GID=$(id -g) \
  docker compose --env-file .env -f scanner/docker/compose.yml run --rm scanner \
  python -m scanner scan <HF_REPO_ID>
```

Hub `org/model` → weights download into `models/org--model/` for the duration of the scan, then **`output/org--model/scan_result.json` is kept** and weights are **deleted automatically** (unless `SCAN_KEEP_WEIGHTS=1` for CLI debugging). Every scan re-downloads from Hugging Face Hub.

## CLI

| Command | Purpose |
|---------|---------|
| `scan` | Full pipeline → `scan_result.json` |
| `refresh-supply-chain` | pip-audit/OSV + TruffleHog only; update existing JSON (no ModelScan rerun) |
| `refresh-supply-chain --all` | Same for every model under `output/` |
| `validate` | Check existing JSON |
| `metadata` | Hub file list only |
| `modelscan` | Debug: ModelScan only |
| `fickling` | Debug: Fickling only |
| `modelaudit` | Debug: ModelAudit only (content-routed) |
| `deps` | Debug: pip-audit + OSV only |
| `secrets` | Debug: TruffleHog only |

## Postgres ingest

Projection of `scan_result.json` into shared Postgres (`qa_ai_models`).
Uses **`dbutils/`** + `scanner/db/load_scans.py` (dry-run default, `--apply` to write).
Frontend `/scans` reads DB when `POSTGRES_DSN` is set, else disk.

See [`scanner/db/README.md`](db/README.md) for schema apply, load, and verify SQL.

## Layout

| Path | Role |
|------|------|
| `scanner/*.py` | Production |
| `experiments/` | OSV, Trivy spikes |
| `../unit_tests/` | Host unit tests (repo root) |
| `models/<slug>/` | HF weights **during** scan; auto-deleted after `scan_result.json` (see `SCAN_KEEP_WEIGHTS`) |
| `output/<slug>/` | Persistent scan JSON + logs (UI / ingest source of truth) |
| `db/` | Postgres schema + loader (`scan_schema.sql`, `load_scans.py`) |

## Source file map 

| Module | Responsibility |
|--------|----------------|
| `__main__.py` | CLI: `scan`, `metadata`, debug subcommands, `validate` |
| `pipeline.py` | Orchestrates download → tools → `scan_result.json` |
| `download.py` | `snapshot_download` into `models/<slug>/` |
| `metadata.py` | Hub file list without weights |
| `format_detector.py` | File categories + `safetensors_only` / Fickling flags |
| `pickle_scan.py` | ModelScan whole-repo + Fickling per pickle-family file |
| `modelaudit_scan.py` | Content-routed ModelAudit + noise filtering |
| `dependency_scan.py` | pip-audit + OSV combiner for dependency manifests |
| `secret_scan.py` | TruffleHog filesystem secret scan |
| `risk_scorer.py` | Merge tools → tier, score, deduped `findings[]` |
| `schemas.py` | Pydantic `ScanResult` / `Finding` (Postgres-ready) |
| `paths.py` | `MODELS_ROOT`, `OUTPUT_ROOT`, slug helpers |
| `report_text.py` | Terminal summaries for debug commands |
