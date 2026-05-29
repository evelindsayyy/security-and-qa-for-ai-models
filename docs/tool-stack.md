# Tool stack

Technical reference for tool choices. Work tracking: [`.gitlab/README.md`](../.gitlab/README.md).

Pipelines: [`track-a-framework.md`](track-a-framework.md) (Track A) · [`track-b-framework.md`](track-b-framework.md) (Track B) · [`gateway-models.md`](gateway-models.md) · [`team-tracks.md`](team-tracks.md) (outcomes)

**Status:** In use | Spike | Planned | Stretch | Not used (summer)

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
| ModelScan | In use | ML file / format scan |
| Fickling | In use | Pickle AST; paired with ModelScan |
| pip-audit | Spike → Planned | Dependency CVEs |
| OSV API | Spike | CVE lookup with pip-audit |
| TruffleHog | Planned | Secrets in model repos |

Spike: `testing/scanning/`

### Safety (inference / red team)

| Tool | Status | Role |
|------|--------|------|
| garak | Planned | Broad automated probes (jailbreak, injection, toxicity, leakage) via LiteLLM |
| promptfoo | Planned | [Declarative red-team YAML](https://github.com/promptfoo/promptfoo), custom graders, CI; Duke policy and academic-integrity suites |
| Duke probes | Planned | Duke-only prompts not covered by garak catalog (may live in `safety/promptfoo/`) |
| LiteLLM guardrails | Planned (doc) | Gateway integration path (ITSO) |

**Division of labor (avoid duplicate prompts):**

| Tool | Owns |
|------|------|
| garak | Wide vulnerability probe catalog, detector pass/fail |
| promptfoo | Curated red-team scenarios, regression in GitLab CI, named policy tests |
| Duke probes | Institutional policy wording if not encoded in promptfoo configs |

Probe categories align with Llama Guard taxonomy. `deployment_context` selects subsets (chatbot vs agentic, guardrails on/off).

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

Track B does **not** own red-team or jailbreak suites — those are Track A **safety**. Track B measures task quality and ops metrics.

Reference only: MT-Bench, AlpacaEval, full SWE-bench, HELM. See [`track-b-framework.md`](track-b-framework.md).

---

## Pipelines

```text
Scanning     → ModelScan + Fickling + deps + secrets → ScanResult   } security pillar
Safety       → garak + promptfoo + Duke probes       → SafetyResult } (Track A)
Efficacy     → Duke tasks + metrics                  → EvalRun      (Track B)
```

---

## Open decisions

| Item | Default |
|------|---------|
| OWASP Dependency-Check vs pip-audit | pip-audit + OSV |
| Watchtower | Skip |
| Trivy (teammate spike) | Defer unless standup adopts |
| PyRIT | Stretch only |
