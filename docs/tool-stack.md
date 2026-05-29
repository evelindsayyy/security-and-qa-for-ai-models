# Tool stack

Quick reference. Pipelines: [`security-framework.md`](security-framework.md) (A), [`evaluation-framework.md`](evaluation-framework.md) (B). Schedule: [`team-tracks.md`](team-tracks.md).

**Status:** In use | Spike | Planned | Stretch | Not used (summer)

---

## Shared

| Tool | Status | Role |
|------|--------|------|
| LiteLLM | In use | Duke AI Gateway; Track A safety probes, Track B evals. Spike: `testing/test_gateway.py` |

---

## Track A — decided stack

One tool per job. Alternatives listed under [Not used](#track-a--not-used-summer) only.

### Security (artifacts, pre-deploy)

| Tool | Status | Role |
|------|--------|------|
| ModelScan | In use | ML file / format scan |
| Fickling | In use | Pickle AST; always paired with ModelScan |
| pip-audit | Spike → Planned | Dependency CVEs (week 4) |
| OSV API | Spike | CVE lookup; complements pip-audit |
| TruffleHog | Planned | Secrets in model repos (week 4) |

Spike: `testing/security_scanning_tests/`

### Safety (gateway / on-prem inference)

| Tool | Status | Role |
|------|--------|------|
| garak | Planned (week 3–4) | Automated red-team probe runs via LiteLLM |
| Duke probes (`safety/`) | Planned | Policy-specific prompts (academic integrity, Duke context) |
| LiteLLM guardrails | Planned (doc, week 5) | Integration path for ITSO |

Probe categories follow Llama Guard taxonomy. Deployment context (`chatbot` / `agentic`, tools, guardrails) selects probe subsets.

### Track A — not used (summer)

| Tool | Reason |
|------|--------|
| PyRIT | Overlaps garak on prompt-based red team; adopt only if multi-turn campaigns are required (stretch, week 10) |
| promptfoo | Overlaps garak + Duke probes on Track A; optional on Track B for efficacy regression only |
| LLM Guard | Overlaps gateway guardrails; document LiteLLM hooks instead of a second middleware pilot |
| ART | Adversarial ML on loaded weights; not HF scan or chat APIs |
| Watchtower | Overlaps ModelScan |
| OWASP Dependency-Check | Use pip-audit + OSV unless gap analysis requires broader SCA |
| Checkmarx, vulnhuntr | Out of scope |
| Heretic | Research only (weight-level bypass limits) |
| CycloneDX | Stretch (week 10 ML-BOM) |

---

## Track B — decided stack

| Tool | Status | Role |
|------|--------|------|
| LiteLLM | In use | Inference |
| Duke YAML suites | Planned | Primary tasks (`tasks/`, rubrics) |
| ROUGE-L | Planned | Summarization |
| LLM-as-judge | Planned | Graded tasks |
| IFEval / DocBench-style | Evaluate | Optional benchmark subsets |
| promptfoo | Evaluate | Optional multi-model matrices only |

Reference only (not in pipeline): MT-Bench, AlpacaEval, full SWE-bench, HELM. See [`evaluation-framework.md`](evaluation-framework.md).

---


```text
HF model  →  ModelScan + Fickling + deps + secrets  →  ScanResult
Gateway   →  garak + Duke probes (LiteLLM)           →  SafetyResult
```

---

## Open decisions

| Item | Default if unresolved |
|------|------------------------|
| OWASP Dependency-Check vs pip-audit | pip-audit + OSV |
| Watchtower | Skip |
| PyRIT | Stretch only |
| promptfoo on Track A | No |
