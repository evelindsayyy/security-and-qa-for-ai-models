# Tool stack

Index: [`README.md`](README.md). Track A approach: [`security-framework.md`](security-framework.md). Track B approach: [`evaluation-framework.md`](evaluation-framework.md).

Status: **In use** | **Spike** | **Planned** | **Evaluate** | **Stretch** | **Out of scope**

---

## LiteLLM (both tracks) — In use

Open-source proxy (MIT). Duke AI Gateway routes through it. Track A uses it for safety probes; Track B for efficacy benchmarks. ITSO asked to document native guardrail hooks (Planned, week 5 docs). Spike: `testing/test_gateway.py`.

---

## Track A — Security and safety

### Artifact security

| Tool | Vendor | Status | Role |
|------|--------|--------|------|
| ModelScan | Protect AI | In use | ML format scanning; 0.8.x skips many files (gap map in progress) |
| Fickling | Trail of Bits | In use | Pickle AST analysis; pair with ModelScan (false positives on legacy `.bin`) |
| OSV API | Google | Spike | CVE lookup without install |
| pip-audit | PyPA | Spike | Dependency audit; production pipeline week 4 |
| TruffleHog | Truffle Security | Planned | Secrets in repos (week 4) |
| OWASP Dependency-Check | OWASP | Evaluate | Broader SCA; compare to pip-audit + OSV |
| Watchtower | AI Shield | Evaluate | Overlaps ModelScan stack; adopt only if gap map justifies |
| CycloneDX | OWASP | Stretch | ML-BOM / SBOM (week 10) |

Spike path: `testing/security_scanning_tests/`

### Safety (inference)

| Tool | Vendor | Status | Role |
|------|--------|--------|------|
| LLM Guard | Protect AI | Evaluate | Input/output scanners (injection, PII, toxicity); MIT, same vendor as ModelScan |
| promptfoo | promptfoo.dev | Evaluate | Red-team YAML suites (Track A); optional efficacy regression (Track B) |
| LiteLLM guardrails | BerriAI | Planned | Document gateway integration (ITSO) |
| Llama Guard taxonomy | Meta | Planned | Hazard categories for probe design |
| Heretic | OSS (p-e-w) | Stretch | Weight-level alignment removal; research/limitations only |

### Out of scope (summer)

Checkmarx (enterprise). vulnhuntr (AI-generated app code, future project). Developer Assist (product TBD).

---

## Track B — Evaluation

| Tool / source | Status | Role |
|---------------|--------|------|
| LiteLLM | In use | Gateway inference |
| Duke YAML suites | Planned | Primary tasks (`tasks/`, rubrics) |
| ROUGE-L | Planned | Summarization overlap (week 3) |
| LLM-as-judge | Planned | Graded tasks (week 5); human validation week 8 |
| promptfoo | Evaluate | Optional multi-model efficacy matrices |
| IFEval, DocBench, QASPER | Evaluate | API-friendly subsets; see `evaluation-framework.md` |
| MT-Bench, AlpacaEval | Reference | Prompt and judge patterns |
| SWE-bench (full) | Out of scope | Requires coding agent + repo; not default gateway eval |
| SWE-bench Lite / HumanEval | Evaluate | Optional coding-snippet column |
| Berkeley Function Calling Leaderboard | Evaluate | Agentic / tool-use scenarios |
| HELM, Chatbot Arena | Reference | External context on nutrition label |

Details: [`evaluation-framework.md`](evaluation-framework.md)

---

## Proposed stack

**Track A:** ModelScan + Fickling + pip-audit/OSV + TruffleHog; LLM Guard or custom probes + promptfoo; LiteLLM transport.

**Track B:** LiteLLM + ROUGE-L + LLM-as-judge + efficacy YAML; ops metrics on every call.

---

## Open decisions (week 2)

- OWASP Dependency-Check vs pip-audit + OSV (one-page comparison)
- LLM Guard pilot: three gateway models, latency and false-positive rate
- promptfoo: five safety probes, three efficacy tasks
- Watchtower: skip unless gap analysis requires it
- LiteLLM guardrail integration path for OIT/ITSO
