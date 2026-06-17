# Track A — scanning and safety (security pillar)

Track A delivers the nutrition label **security** pillar through two parts: **scanning** (artifacts) and **safety** (inference / red team).

Track B: [`track-b-framework.md`](track-b-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

---

## How terms map

| Term | Meaning |
|------|---------|
| **Security** (pillar) | What OIT publishes on the nutrition label — combines scanning + safety |
| **Scanning** | Pre-deploy artifact checks (HF / on-prem files) |
| **Safety** | Inference-time harm, policy, red team (gateway / on-prem) |
| **Track A** | Team that builds `scanner/` (scanning) and `safety/` (safety) |

---

## Scanning (artifacts)

When: before on-prem or HF weights are deployed.  
Where: **`scanner/`** only (code, `models/`, `output/` on DGX; spikes in `scanner/experiments/`).

```text
model_id → metadata (optional) → download → ModelScan + Fickling + ModelAudit
         → pip-audit / OSV → TruffleHog → risk scorer → ScanResult
```

| Step | Implementation |
|------|----------------|
| Metadata | `scanner/metadata.py` (`python -m scanner metadata`) |
| Download | `scanner/download.py` (via `python -m scanner scan`) |
| Pickle / format | ModelScan + Fickling (all pickle-family files) + ModelAudit (content-routed); merged in risk scorer |
| Dependencies | pip-audit + OSV |
| Secrets | TruffleHog |

Gateway-only models today: scanning is lower priority until on-prem OSS. Runs in isolated Docker workers, not in the API process.

**Model catalog:** Gateway IDs and test tiers — [`gateway-models.md`](gateway-models.md). **Do not** run ModelScan on cloud gateway APIs; safety/eval use LiteLLM only.

---

## Safety (inference / red team)

When: gateway or on-prem chat endpoints are live.  
Where: `safety/`.

```text
model_ids + deployment_context
    → garak (broad probes)
    → promptfoo (YAML red-team suites)
    → Duke policy probes (if needed)
    → SafetyResult
```

| Tool | Role |
|------|------|
| [garak](https://github.com/NVIDIA/garak) | Automated vulnerability-style probe sweep via LiteLLM |
| [promptfoo](https://github.com/promptfoo/promptfoo) | Declarative red-team configs, graders, CI-friendly regression |
| Duke probes | Duke-specific policy and academic-integrity scenarios |

---

## Output

Normalized shapes: [`data-model.md`](data-model.md) (`scans`/`findings`, `safety_runs`/`safety_findings`). Tools run, capture raw JSON, and map into Pydantic in `scanner/` and `safety/`; an ingest step loads that JSON into Postgres (see [`architecture.md`](architecture.md#why-json--postgres)).

| Part | Output (JSON today) | Production |
|------|---------------------|------------|
| Scanning | `scanner/` → `scanner/output/<slug>/scan_result.json` (Docker: `scanner/docker/`) | Postgres (ingest) |
| Safety | `safety/` → `safety/output/<slug>/merged_safety_result.json` (`run_safety.sh` → `safety.merge`) | Postgres (ingest) |

---

## Calibration (gpt2, DGX 2026-06-02)

| Signal | Result |
|--------|--------|
| `scan_result.json` | `severity_tier`: low, `overall_risk_score`: 18 |
| ModelScan 0.8.8 | 0 issues on gpt2; many paths skipped by extension (ModelAudit covers gaps) |
| Fickling | LIKELY_UNSAFE on `pytorch_model.bin` (benign stacked pickle) |
| distilbert-base-uncased | Same pattern (score 18, low) |
| `neimasilk/modelscan-extension-mismatch-poc` | critical / 95; ModelScan 0 issues; extensionless payload flagged |

Do not block deploy on Fickling alone when ModelScan and ModelAudit are clean. See `scan_metadata.coverage` in `scan_result.json` for per-run tool reach.

---

## Metadata vs full download

| Goal | Metadata only | Full download |
|------|---------------|---------------|
| Inventory / label fields | Yes | No |
| ModelScan / Fickling | No | Yes |

---

## Package roadmap (`scanner/` and `safety/`)

| Stage | `scanner/` | `safety/` |
|-------|------------|-----------|
| Done | package + CLI; deps, secrets, E2E `scan_model()` | `garak` + `promptfoo` + Duke probes; merge → `MergedSafetyResult` on gateway models |
| Next | Background job launcher + ingest `ScanResult` → Postgres | ingest `MergedSafetyResult` → Postgres; full label UI in `frontend/` |

Target layout: [`scanner/README.md`](../scanner/README.md), [`docs/architecture.md`](architecture.md).

---

## Known limitations (scanning)

ModelScan 0.8.x is extension-routed; **ModelAudit** adds content-based coverage on candidate files. Fickling flags benign PyTorch weight pickles. **Safetensors-only** repos: Fickling does not apply; use format flags in `scan_metadata.file_formats`. **ModelAudit** uses content detection (including extensionless/rename bypass cases). Overlapping tool output is deduped in `risk_scorer.py`; tier is max across tools. Risk merge: **[`scanner/README.md`](../scanner/README.md)**. Static scanning does not detect poisoned weights or all obfuscated payloads.
