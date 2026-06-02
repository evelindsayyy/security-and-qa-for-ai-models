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
Where: `scanner/` (production), `testing/scanning/` (spike).

```text
model_id → metadata (optional) → download → ModelScan + Fickling
         → pip-audit / OSV → TruffleHog → risk scorer → ScanResult
```

| Step | Implementation |
|------|----------------|
| Metadata | `list_model_metadata.py` |
| Download | `download_model.py` |
| Pickle / format | ModelScan + Fickling |
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

Normalized shapes: [`data-model.md`](data-model.md) (`scans`/`findings`, `safety_runs`/`safety_findings`). Week 3: run tools, capture raw JSON, map into Pydantic in `scanner/` and `safety/` before Postgres (week 5).

| Part | Spike (learn tool output) | Production |
|------|---------------------------|------------|
| Scanning | `testing/scanning/` → `ScanResult` in `schemas.py` | `scanner/` → JSON then Postgres |
| Safety | Run garak / promptfoo; sample output in issue | `safety/` → `SafetyResult` JSON |

---

## Calibration (GPT-2, 2026-05-27)

Known-safe baseline on DGX (scanning).

| Signal | Result |
|--------|--------|
| ModelScan | 0 issues on scanned pickles |
| ModelScan | 212 files skipped (gap map in progress) |
| Fickling | LIKELY_UNSAFE on `pytorch_model.bin` (benign legacy pickle) |

Do not block deploy on Fickling alone. Risk scorer must merge ModelScan and Fickling. Distilbert shows the same pattern.

---

## Metadata vs full download

| Goal | Metadata only | Full download |
|------|---------------|---------------|
| Inventory / label fields | Yes | No |
| ModelScan / Fickling | No | Yes |

---

## Package roadmap (`scanner/` and `safety/`)

| Week | `scanner/` | `safety/` |
|------|------------|-----------|
| W2 | Spike only (`testing/scanning/`) | Schemas only (slipped) |
| W3 | Extract package; `risk_scorer`, `pipeline` v0 | `garak_runner`, `promptfoo/`, probes v0 |
| W4 | deps, secrets, E2E `scan_model()` | Pilot 3 gateway models |
| W5 | Celery worker integration | Celery worker; writes `safety_runs` |
| W6 | — | UI in `frontend/` (reads `api/`) |

Target layout: [`scanner/README.md`](../scanner/README.md), [`docs/architecture.md`](architecture.md).

---

## Known limitations (scanning)

ModelScan 0.8.x skips many file types. Fickling flags benign PyTorch weight pickles. Static scanning does not detect poisoned weights, trigger backdoors, or heavily obfuscated payloads. Document fully by handoff (week 9).
