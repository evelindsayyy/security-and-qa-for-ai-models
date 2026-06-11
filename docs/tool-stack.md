# Tool stack

Technical reference for tool choices. Work tracking: [`.gitlab/README.md`](../.gitlab/README.md).

Pipelines: [`track-a-framework.md`](track-a-framework.md) (Track A) · [`track-b-framework.md`](track-b-framework.md) (Track B) · [`gateway-models.md`](gateway-models.md) · [`team-tracks.md`](team-tracks.md) (outcomes)

**Status:** In use | Spike | Planned | Stretch | Not used 

---

## Shared

| Tool | Status | Role |
|------|--------|------|
| LiteLLM | In use | Duke AI Gateway; Track A safety, Track B efficacy (`testing/test_gateway.py`) |

---

## Track A (security pillar)

### Scanning (artifacts, pre-deploy)

| Tool | Status | Role |
|------|--------|------|
| ModelScan | In use | Pickle / H5 / SavedModel; extension-routed (complemented by ModelAudit) |
| Fickling | In use | Pickle AST on every pickle-family weight file; paired with ModelScan |
| ModelAudit | In use | Content-routed directory scan (`scanner/modelaudit_scan.py`); findings deduped in risk scorer |
| pip-audit | In use | Python dependency CVEs (primary for requirements files) |
| OSV API | In use | Corroborates pip-audit; covers non-Python manifests (npm, Go, etc.) |
| TruffleHog | In use | Secrets in model repos (filesystem mode) |

Run: `scanner/` via Docker (`scanner/docker/` → `scanner/models`, `scanner/output`)

### Safety (inference / red team)

| Tool | Status | Role |
|------|--------|------|
| garak | In use | Broad automated probes (jailbreak, injection, toxicity, leakage) via LiteLLM (`safety/garak/`) |
| promptfoo | In use | [Declarative red-team YAML](https://github.com/promptfoo/promptfoo), custom graders, CI; Duke policy and academic-integrity suites (`safety/promptfoo/`) |
| Duke probes | In use | Duke-only prompts in the promptfoo policy config (`safety/promptfoo/promptfooconfig.yaml`) |
| LiteLLM guardrails | Planned (doc) | Gateway integration path (ITSO) |

Run: `./safety/run_safety.sh "GPT 4.1 Mini"` → per-tool exports merged by `python -m safety.merge` into `safety/output/<model>/merged_safety_result.json`.

### Not used (summer)

| Tool | Reason |
|------|--------|
| PyRIT | Overlaps garak/promptfoo; stretch only if multi-turn campaigns required |
| LLM Guard | Overlaps gateway guardrails; document LiteLLM hooks instead |
| ART | Adversarial ML on loaded weights; not HF scan or chat APIs |
| Watchtower | Overlaps ModelScan |
| OWASP Dependency-Check | Default: pip-audit + OSV |
| Checkmarx, vulnhuntr | Out of scope |
| Heretic | Research only |
| CycloneDX | Stretch (ML-BOM) |

---

## Track B (efficacy pillar)

| Tool | Status | Role |
|------|--------|------|
| LiteLLM | In use | Gateway inference |
| Duke YAML suites | Planned | Primary efficacy tasks (`tasks/`, rubrics) |
| ROUGE-L | Planned | Summarization |
| LLM-as-judge | Planned | Graded tasks |
| IFEval / DocBench-style | Evaluate | Optional benchmark subsets |

Reference: MT-Bench, AlpacaEval, full SWE-bench, HELM. See [`track-b-framework.md`](track-b-framework.md).

---

## Pipelines

```text
Scanning     → ModelScan + Fickling + ModelAudit + pip-audit/OSV + TruffleHog → ScanResult   } security pillar
Safety       → garak + promptfoo + Duke probes       → SafetyResult } (Track A)
Efficacy     → Duke tasks + metrics                  → EvalRun      (Track B)
```

---

## Open decisions

| Item | Default |
|------|---------|
| OWASP Dependency-Check vs pip-audit | pip-audit + OSV (implemented) |
| Watchtower | Skip |
| Trivy | FS/CVE spike in `scanner/experiments/`; defer for weights |
| PyRIT | Stretch only |

**Dependency scanning:** pip-audit resolves Python requirement trees; OSV API corroborates hits (`corroborated_by: ["osv"]`) and scans non-Python manifests when present.
