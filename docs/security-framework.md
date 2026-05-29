# Security and safety framework (Track A)

Reference for **Raphael and Nithi**. Track B evaluation: [`evaluation-framework.md`](evaluation-framework.md). Tools: [`tool-stack.md`](tool-stack.md). Schedule: [`team-tracks.md`](team-tracks.md).

---

## Scope

| Pillar | When | What |
|--------|------|------|
| **Security** | Pre-deploy (HF / on-prem files) | Pickle exploits, dependency CVEs, secrets in repos |
| **Safety** | Inference (gateway or on-prem) | Harm, policy violations, jailbreaks, red team |

**Today:** Gateway models need safety probes; file scanning ramps up when on-prem OSS lands.  
**Isolation:** Scans run in Docker workers only — never in the API process.

**Tests (current):** `testing/security_scanning_tests/` on DGX.

---

## Artifact pipeline (security)

```text
model_id  →  metadata listing (optional)  →  download if needed  →  modelscan + fickling
           →  pip-audit / OSV (week 4)  →  trufflehog (week 4)  →  risk scorer  →  ScanResult
```

| Step | Tool / code |
|------|-------------|
| Inventory without weights | `list_model_metadata.py` (HF API) |
| Full artifact download | `download_model.py` |
| Pickle / format scan | ModelScan + Fickling |
| Dependencies | pip-audit + OSV API |
| Secrets | TruffleHog (planned) |

---

## Safety pipeline (week 3+)

Probes via LiteLLM to Duke AI Gateway. Probe categories follow Llama Guard taxonomy (harm, academic dishonesty, PII, jailbreaks). Deployment context (chatbot vs agentic, tools, guardrails) changes probe set per ITSO.

Tools under evaluation: LLM Guard, promptfoo (red team). Academic-dishonesty prompts are **safety**, not Track B efficacy.

---

## Scan output format

Spike writes JSON under `testing/security_scanning_tests/output/<model>/`. Production target: `scanner/` + Postgres.

### Combined report (spike)

| Field | Meaning |
|-------|---------|
| `severity_tier` | From ModelScan counts today (low / medium / high / critical) |
| `fickling_severity` | Separate Fickling signal until week 3 reconciler |
| `overall_risk_score` | Placeholder `0` until rubric defined |
| `findings` | Structured issues (empty in spike) |
| `tool_results` | Trimmed ModelScan + Fickling summaries |

### Spike vs production

| Spike now | Production (week 3+) |
|-----------|----------------------|
| Modelscan-only tier | Weighted merge of all tools |
| `overall_risk_score: 0` | 0–100 score on nutrition label |
| Full skipped-file list in `modelscan_report.json` | Gap map documented; DB audit trail |

Pydantic shapes: `ScanRequest`, `ScanResult`, `Finding` in `testing/security_scanning_tests/schemas.py`.

---

## Calibration: GPT-2 (2026-05-27)

First DGX scan on a **known-safe** model — baseline for false-positive tuning.

| Signal | Result |
|--------|--------|
| ModelScan | 0 issues; scanned `pytorch_model.bin` and `rust_model.ot` pickles |
| ModelScan skipped | 212 files (coverage gap — gap map in progress) |
| Fickling | LIKELY_UNSAFE on `pytorch_model.bin` |
| Fickling format | `pytorch_stacked_pickle`, stack_count 5 |

**Implications:** Do not block on Fickling alone on legacy PyTorch `.bin` files. Week 3 risk scorer must merge ModelScan and Fickling explicitly.

Artifact (local, gitignored): `testing/security_scanning_tests/output/gpt2/combined_scan.json`

Distilbert shows the same pattern (0 ModelScan issues, Fickling often LIKELY_UNSAFE) — expected on benign PyTorch pickles.

---

## When to download vs metadata only

| Need | Metadata only | Full download |
|------|---------------|---------------|
| File inventory, nutrition label fields | Yes | No |
| modelscan / fickling | No | Yes |
| Dependency file content | List + optional single-file fetch | Optional full tree |

---

## Week 2 complete (Track A spike)

- Docker spike: modelscan, fickling, combined JSON
- OSV vs pip-audit comparison script
- Metadata listing script
- Pydantic schemas + isolation notes

## Week 2 remaining

- ModelScan gap map (skipped file types)
- Scope lock in docs
- Tool decisions (OWASP Dependency-Check, Watchtower, LLM Guard pilot plan)
- LiteLLM guardrail integration path (document only)
- `SafetyResult` schema; safety probe plan (implementation week 3+)

---

## Limitations (document for week 9)

- ModelScan skips many file types in 0.8.x
- Fickling false positives on standard PyTorch weights
- Cannot detect poisoned weights, trigger backdoors, or heavy obfuscation from static scan alone
- Weight-level guardrail bypass (e.g. research tools like Heretic) — inference guardrails insufficient alone
