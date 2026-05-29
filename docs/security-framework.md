# Security and safety (Track A)

Track B: [`evaluation-framework.md`](evaluation-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

---

## Scope

| Pillar | When | What |
|--------|------|------|
| Security | Pre-deploy (HF / on-prem files) | Pickle risk, CVEs, secrets |
| Safety | Inference (gateway / on-prem) | Harm, policy, jailbreaks |

Gateway models: safety first. File scanning ramps up for on-prem OSS. Scans run in Docker workers only (not in the API process).

Spike: `testing/security_scanning_tests/`

---

## Pipelines

**Security**

```text
model_id → metadata (optional) → download → ModelScan + Fickling
         → pip-audit / OSV → TruffleHog → risk scorer → ScanResult
```

| Step | Implementation |
|------|----------------|
| Metadata | `list_model_metadata.py` |
| Download | `download_model.py` |
| Pickle / format | ModelScan + Fickling |
| Dependencies | pip-audit + OSV (week 4) |
| Secrets | TruffleHog (week 4) |

**Safety (week 3+)**

```text
model_ids + deployment_context → garak (LiteLLM) + Duke probes → SafetyResult
```

Academic-dishonesty prompts are safety, not Track B efficacy.

---

## Output

Spike JSON: `testing/security_scanning_tests/output/<model>/`. Production: `scanner/`, `safety/`, Postgres.

| Field (spike) | Notes |
|---------------|-------|
| `severity_tier` | ModelScan-based until week 3 reconciler |
| `fickling_severity` | Separate until merged in risk scorer |
| `overall_risk_score` | Placeholder `0` until rubric |

Schemas: `ScanRequest`, `ScanResult`, `Finding` in `schemas.py`.

---

## Calibration (GPT-2, 2026-05-27)

Known-safe baseline on DGX.

| Signal | Result |
|--------|--------|
| ModelScan | 0 issues on scanned pickles |
| ModelScan | 212 files skipped (gap map in progress) |
| Fickling | LIKELY_UNSAFE on `pytorch_model.bin` (benign legacy pickle) |

Do not block on Fickling alone. Week 3 scorer merges both signals. Distilbert shows the same pattern.

---

## Metadata vs full download

| Goal | Metadata only | Full download |
|------|---------------|---------------|
| Inventory / label fields | Yes | No |
| ModelScan / Fickling | No | Yes |

---

## Status

**Done (week 2 spike):** Docker scan, OSV vs pip-audit script, metadata listing, Pydantic schemas, isolation notes.

**Next:** ModelScan gap map; `SafetyResult` schema; garak pilot (week 3–4); risk reconciler; `scanner/` / `safety/` extraction.

**Limits (week 9 doc):** ModelScan file-type gaps; Fickling FP on standard weights; no detection of poisoned weights or obfuscated payloads from static scan alone.
