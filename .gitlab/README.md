# GitLab — project work items (Track A + Track B + Team)

Copy issues into **Work items**; track status only in GitLab. Open-source docs in `docs/` — this file is the **execution plan** through week 6 (detail) and week 7+ (titles).

| What | Where |
|------|--------|
| Architecture, tools, pipelines | `docs/` |
| Gateway model names, test tiers | [`docs/gateway-models.md`](../docs/gateway-models.md) |
| DB schema, JSON shapes | [`docs/data-model.md`](../docs/data-model.md) |
| Tasks, milestones, issues | **This file → GitLab** |

| Track | Members | Title prefix | Label |
|-------|---------|--------------|-------|
| **A** — Scanning & Safety | Raphael, Nithi | `[Track A]` | `track-a` |
| **B** — Evaluation | Grace, Jack | `[Track B]` | `track-b` |
| **Team** — shared | Everyone | `[Team]` | `team-shared` |

**Not Track A only.** Sections 4–6 are per track; section 3 is collaboration; section 8 is shared schema/UI.

---

## Table of contents

1. [Naming, labels, milestones](#1-naming-labels-milestones)
2. [Model testing strategy (gateway vs HF)](#2-model-testing-strategy-gateway-vs-hf)
3. [Structured outputs and database](#3-structured-outputs-and-database)
4. [Package structure: scanner/ and safety/](#4-package-structure-scanner-and-safety)
5. [GitLab setup (step-by-step)](#5-gitlab-setup-step-by-step)
6. [Track collaboration by week](#6-track-collaboration-by-week)
7. [Track A issues W2–W6 (detail)](#7-track-a-issues-w2w6-detail)
8. [Track B issues W2–W6 (direction)](#8-track-b-issues-w2w6-direction)
9. [Team issues W2–W6](#9-team-issues-w2w6)
10. [Templates](#10-templates)

---

## 1. Naming, labels, milestones

### Titles

| Prefix | Example |
|--------|---------|
| `[Track A]` | `[Track A][W4] garak pilot — gateway model tier` |
| `[Track B]` | `[Track B][W3] Multi-model gateway runner` |
| `[Team]` | `[Team][W5] Postgres schema migration v1` |

### Labels

`track-a` · `track-b` · `team-shared` · `scanning` · `safety` · `red-team` · `gateway` · `efficacy` · `evaluator` · `frontend` · `mvp` · `spike` · `docs` · `blocked` · `stretch`

- **`gateway`** — issue involves Duke AI Gateway model IDs (not HF DGX scan)
- **`scanning`** — HF artifact pipeline only

### Shared milestones (whole team — no labels on milestones)

| Milestone | Due | One-line goal |
|-----------|-----|----------------|
| `W2 — Foundation` | End W2 | Spikes, schemas, model catalog, CI |
| `W3 — Core pipelines` | End W3 | Structured JSON per track; 1 gateway safety run |
| `W4 — E2E & tests` | End W4 | Full scan pipeline; safety pilot 3 gateway models |
| `W5 — API & integration` | End W5 | Postgres + Celery + `/scans` `/safety` `/evals` |
| `W6 — Dashboard` | End W6 | Nutrition label UI for all pillars |
| `W7 — MVP demo (freeze)` | Demo | Full gateway catalog |
| `W8–W9 — Hardening & handoff` | | FP study, judge validation, docs |
| `W10 — Stretch` | | Optional |

Paste full milestone descriptions from [§5 step 2](#step-2--create-milestones) when creating in GitLab.

---

## 2. Model testing strategy (gateway vs HF)

Duke uses **two different “models” concepts**:

| Concept | Where tested | Track A part | Examples |
|---------|--------------|----------------|----------|
| **HF repo** (`model_id`) | DGX Docker spike / `scanner/` | **Scanning** | `gpt2`, `distilbert-base-uncased`, `facebook/opt-125m` |
| **Gateway model** (LiteLLM `model=` string) | Duke AI Gateway API | **Safety** (and Track B efficacy) | `GPT 4.1 Mini`, `Llama 4 Scout`, `GPT-5-mini` |

**Mistral:** phased out — **do not** add new Mistral tests. Remove from catalog when OIT confirms.

**Closed-source (cloud):** Most gateway chat models (GPT-5.x, GPT-4.1, Llama 3.3 / 4) — no local weights; **no scanning** until/if hosted on-prem with HF repo.

**Open-source (future on-prem):** When OIT hosts Llama 4 / GPT-OSS on GPU, add **scanning** for that HF repo **and** keep **safety** on gateway endpoint.

Canonical list and costs: [`docs/gateway-models.md`](../docs/gateway-models.md).

### Track A test tiers (timeline impact)

| Week | Scanning (HF on DGX) | Safety (gateway) |
|------|----------------------|------------------|
| **W2** | Regression: distilbert, gpt2, opt-125m | promptfoo + gateway **smoke**: 1 cheap model (`GPT 4.1 Mini` or `GPT-5-nano`) |
| **W3** | risk scorer; `scanner/` extract | garak + promptfoo + Duke probes on **1** gateway model |
| **W4** | deps + secrets + E2E ScanResult | **Pilot 3** gateway models (1 OpenAI, 1 Llama 4, 1 mini) — see below |
| **W5** | Persist scans to Postgres | Persist safety runs; same 3 models minimum |
| **W6** | UI shows last scan per model | UI safety heatmap **per gateway model** |
| **W7** | ≥3 HF samples for demo | **All** general chat gateway models (skip specialty unless needed) |

**W4 pilot trio (confirm IDs with OIT):**

1. `GPT 4.1 Mini` (or `GPT-4.1-mini` — match gateway exactly)
2. `Llama 4 Scout` (or `Llama 4 Maverick`)
3. `GPT-5-nano` or `GPT-5-mini` (cost control)

**Do not** bulk red-team `GPT-5.4-pro` or specialty codex/transcribe models in W4 — document as out-of-scope in issue.

### Track B (direction only)

Grace/Jack pick gateway models for efficacy using **same catalog** and cost constraints. Relate to `[Team][W2] Gateway model catalog` for IDs. Track B may add tools beyond this README — keep `EvalRun` / `TaskResult` compatible with [`docs/data-model.md`](../docs/data-model.md).

---

## 3. Structured outputs and database

| Output | Producer | Spike today | Postgres (W5+) |
|--------|----------|-------------|----------------|
| `ScanResult` + `Finding[]` | scanning | `combined_scan.json` | `scans`, `findings` |
| `SafetyResult` + category rows | safety | TBD JSON | `safety_runs`, `safety_findings` |
| `EvalRun` + `TaskResult[]` | Track B | TBD | `eval_runs`, `eval_results` |

Full ER diagram and `deployment_context`: [`docs/data-model.md`](../docs/data-model.md).

### Team-owned (W2 design, W5 implement)

- `models` table: `gateway_model_id`, optional `hf_repo`, `provider`, `deployment_type`, `deployment_context` JSONB
- Nutrition label aggregate: `GET /models/{id}` returns `security.scanning`, `security.safety`, `efficacy`

### Track A GitLab issues for schema

| Week | Issue |
|------|-------|
| W2 | `[Track A][W2] SafetyResult and SafetyRequest schemas` |
| W2 | `[Track A][W2] Align ScanResult with data-model.md` (task under schemas) |
| W3 | `[Track A][W3] Safety JSON sample for one gateway model` |
| W5 | Relate to `[Team][W5] Postgres schema migration v1` |

---

## 4. Package structure: scanner/ and safety/

Extract from `testing/security_scanning_tests/` starting W3.

```text
scanner/
  __init__.py
  schemas.py          # ScanRequest, ScanResult, Finding
  metadata.py         # list_model_metadata
  download.py
  pickle_scan.py      # modelscan + fickling
  deps.py             # pip-audit + OSV (W4)
  secrets.py          # TruffleHog (W4)
  risk_scorer.py      # W3
  pipeline.py         # scan_model(hf_repo) -> ScanResult
  README.md

safety/
  __init__.py
  schemas.py          # SafetyRequest, SafetyResult
  garak_runner.py
  promptfoo/
    promptfooconfig.yaml
  probes/               # Duke YAML or Python
  pipeline.py         # run_safety(gateway_model_id, context) -> SafetyResult
  README.md
```

Spike remains runnable until W4 E2E replaces it.

---

## 5. GitLab setup (step-by-step)

### Step 1 — Labels and milestones

Create labels ([§1](#labels)). Create milestones W2–W10 ([§1 table](#shared-milestones-whole-team--no-labels-on-milestones)).

### Step 2 — Milestone descriptions (paste into GitLab)

**W2 — Foundation**

```markdown
## Goal
Foundation: data model, Docker, CI, UI mockups; close scanning spike; efficacy framework start.

## Model / catalog
- Confirm gateway LiteLLM IDs with OIT (see docs/gateway-models.md)
- Mistral deprecated — exclude

## Track A
- HF scan regression (gpt2, distilbert, opt-125m)
- SafetyResult schema; promptfoo gateway smoke (1 model)

## Track B
- Eval schemas; task loader; gateway smoke (direction)

## Team
- deployment_context; Docker Compose; GitLab CI
```

**W3 — Core pipelines**

```markdown
## Goal
Structured JSON from HF scan and gateway safety; Track B first eval path.

## Track A
- scanner/ + safety/ packages started
- 1 gateway model: full safety v1 (garak + promptfoo)

## Track B
- Multi-model runner; ROUGE-L; IT support E2E (their tooling)
```

**W4 — E2E & tests**

```markdown
## Goal
Scan pipeline complete; safety on 3 gateway models; evaluator tests (Track B).

## Track A
- ScanResult E2E; garak + promptfoo on pilot trio
```

**W5 — API & integration**

```markdown
## Goal
Postgres + Celery + REST; tracks persist results. Heavy collaboration.

## Team
- Schema migration; /scans /safety /evals
```

**W6 — Dashboard**

```markdown
## Goal
Model list + detail UI; security (scanning + safety) + efficacy panels.
```

**W7 — MVP demo (freeze)**

```markdown
## Goal
Full gateway safety + HF scan samples; feature freeze.
```

### Steps 3–9

3. Create anchor issues: `[Track A][MVP] Security pillar…`, `[Track B][MVP] Efficacy…`, `[Team] Nutrition label…` (milestone W7)  
4. Create W2 issues from [§7](#7-track-a-issues-w2w6-detail) and [§8](#8-track-b-issues-w2w6-direction) and [§9](#9-team-issues-w2w6)  
5. Child **Tasks** under each issue  
6. **Related issues** links for integration (especially W5–W6)  
7. MR: `Closes #N`  
8. Each Monday: add next week’s issues only  

---

## 6. Track collaboration by week

| Week | Integration point | GitLab action |
|------|-------------------|---------------|
| W2 | `deployment_context`, gateway catalog | Team issue; A + B **relate** |
| W3 | Same LiteLLM env vars | Document in Team issue; link test_gateway.py |
| W4 | Model list stable enough for pilots | Comment on catalog issue |
| **W5** | **Postgres + API** | Team leads; A `/scans` `/safety`, B `/evals` |
| **W6** | **Frontend** | Team #1; A scanning+safety panels, B efficacy charts |
| W7 | Demo script | Team issue |

---

## 7. Track A issues W2–W6 (detail)

Copy each block into **New item → Issue**. Add **Tasks** as children.

---

### W2 — Foundation

**Parent:** `[Track A][W2] Close scanning spike` — `track-a`, `spike`, `mvp`

**Tasks:** Docker regression distilbert · gpt2 · opt-125m · Trivy decision comment

---

#### `[Track A][W2] Gateway vs HF test matrix (documentation)`

**Labels:** `track-a`, `docs`, `gateway`, `scanning`, `safety`, `mvp`

```markdown
## User story
As the team, I want a written test matrix for which models are tested how, so we do not run ModelScan on gateway APIs or red-team HF repos by mistake.

## Acceptance criteria
- [ ] Table in docs/gateway-models.md: columns HF scan / gateway safety / gateway efficacy
- [ ] Mistral marked deprecated
- [ ] W2–W4 tier column (smoke / pilot / demo)
- [ ] Link from track-a-framework.md
```

**Tasks:** Sync with OIT on exact LiteLLM IDs; paste into gateway-models.md

---

#### `[Track A][W2] ModelScan coverage gap map`

**Labels:** `scanning`, `docs`, `mvp`

```markdown
## Acceptance criteria
- [ ] Aggregate skipped_files from gpt2 modelscan_report.json
- [ ] Table in docs/track-a-framework.md
```

---

#### `[Track A][W2] SafetyResult and SafetyRequest schemas`

**Labels:** `safety`, `mvp`

```markdown
## Acceptance criteria
- [ ] Pydantic models: SafetyRequest, SafetyResult, SafetyFinding (or equivalent)
- [ ] Fields: gateway_model_id, deployment_context, probe_results[], tool_results{garak, promptfoo}
- [ ] schemas_demo_safety.py validates sample JSON
- [ ] Document mapping to docs/data-model.md tables
```

**Tasks:** Draft JSON from one mock gateway run; review with Team data-model issue

---

#### `[Track A][W2] promptfoo gateway smoke (one model)`

**Labels:** `safety`, `red-team`, `gateway`, `mvp`

```markdown
## Acceptance criteria
- [ ] promptfoo config targets LiteLLM (same .env as test_gateway.py)
- [ ] One model: GPT 4.1 Mini (confirm string with OIT)
- [ ] One red-team prompt passes; output saved under testing/ or issue attachment
- [ ] Note mapping to SafetyResult.tool_results.promptfoo
```

---

#### `[Track A][W2] LiteLLM guardrail path (doc)`

**Labels:** `docs`

---

#### `[Track A][W2] Trivy vs pip-audit decision`

**Labels:** `scanning`, `spike`

---

#### `[Track A][W2] Align ScanResult with team data model`

**Labels:** `scanning`, `team-shared`, `mvp`

```markdown
## Acceptance criteria
- [ ] ScanResult fields documented in docs/data-model.md
- [ ] Comment on Team data-model issue with proposed scan/finding columns
```

**Relate:** `[Team][W2] Data model`

---

### W3 — Core pipelines

**Parent:** `[Track A][W3] Scanning + safety v1 on gateway` — `mvp`

```markdown
## Acceptance criteria
- [ ] ScanResult with merged risk scorer from HF run
- [ ] SafetyResult JSON from one gateway model (garak + promptfoo + Duke probes)
- [ ] scanner/ and safety/ directories exist with README
```

| Issue | Labels | Key tasks (child) |
|-------|--------|-------------------|
| `[Track A][W3] Risk scorer merges ModelScan and Fickling` | `scanning`, `mvp` | Implement risk_scorer.py; unit test gpt2; wire combined_scan |
| `[Track A][W3] Extract scanner/ from spike` | `scanning`, `mvp` | Package layout §4; smoke one HF model |
| `[Track A][W3] Format detector v0` | `scanning`, `mvp` | safetensors/pickle/onnx/config flags in ScanResult |
| `[Track A][W3] garak runner — one gateway model` | `safety`, `red-team`, `gateway`, `mvp` | Install garak; LiteLLM target; jailbreak+toxicity subset; map to SafetyResult |
| `[Track A][W3] promptfoo red-team config v1` | `safety`, `red-team`, `gateway`, `mvp` | safety/promptfoo/; academic integrity + jailbreak prompts |
| `[Track A][W3] Duke policy probe set` | `safety`, `mvp` | 5–10 prompts; no overlap with Track B efficacy |
| `[Track A][W3] deployment_context on safety jobs` | `safety`, `team-shared`, `mvp` | Schema match Team; table: chatbot vs agentic → probe sets |

**Gateway model for W3:** **one** smoke-tier model only (cost).

**Output artifact issue (optional task on parent):** Save `safety/output/<gateway_slug>/safety_result.json` for schema demo.

---

### W4 — E2E & tests

**Parent:** `[Track A][W4] Scan E2E + safety pilot trio` — `mvp`

| Issue | Labels | Acceptance criteria |
|-------|--------|---------------------|
| `[Track A][W4] pip-audit and OSV in scan pipeline` | `scanning`, `mvp` | Findings in ScanResult |
| `[Track A][W4] TruffleHog in scan pipeline` | `scanning`, `mvp` | Secrets → Finding |
| `[Track A][W4] E2E scan_model(hf_repo) -> ScanResult` | `scanning`, `mvp` | CLI documented in scanner/README |
| `[Track A][W4] garak pilot — 3 gateway models` | `safety`, `gateway`, `mvp` | One report per model; summary table in issue |
| `[Track A][W4] promptfoo pilot — 3 gateway models` | `safety`, `gateway`, `mvp` | Same trio; no duplicate prompts vs garak |
| `[Track A][W4] Unit tests scanner pipeline` | `scanning`, `mvp` | test_risk_scorer gpt2 fixture |

**Tasks under garak/promptfoo pilots (per model):**

- Run garak with LiteLLM for model A / B / C  
- Run promptfoo eval for model A / B / C  
- Attach pass/fail summary table to parent issue  

---

### W5 — API & integration

| Issue | Labels | Notes |
|-------|--------|-------|
| `[Track A][W5] Celery scan worker (Docker isolation)` | `scanning`, `team-shared`, `mvp` | **Relate** Team Postgres + API |
| `[Track A][W5] Celery safety worker` | `safety`, `team-shared`, `mvp` | garak + promptfoo; writes safety_runs |
| `[Track A][W5] POST/GET /scans` | `scanning`, `team-shared`, `mvp` | Track A owns payload/response |
| `[Track A][W5] POST/GET /safety` | `safety`, `team-shared`, `mvp` | Include gateway_model_id + deployment_context |
| `[Track A][W5] Persist ScanResult + SafetyResult to Postgres` | `team-shared`, `mvp` | **Relate** Team migration issue |

**Tasks:** Map Pydantic → SQLAlchemy models; integration test one HF scan + one gateway safety job.

---

### W6 — Dashboard

| Issue | Labels | Notes |
|-------|--------|-------|
| `[Track A][W6] Scanning findings drill-down UI` | `scanning`, `frontend`, `team-shared`, `mvp` | **Relate** #1 Dashboard |
| `[Track A][W6] Safety heatmap per gateway model` | `safety`, `frontend`, `team-shared`, `mvp` | Categories × pass/fail; garak + promptfoo sources |
| `[Track A][W6] Model list security status columns` | `team-shared`, `mvp` | Last scan risk + safety summary |

**Tasks:** Agree wireframes with Grace; API fields from `GET /models/{id}`.

---

### W7+ (titles only)

W7: All gateway safety · HF scan samples · Known gaps · Red-team summary  
W8–W9: FP study · runbooks · ADR  
W10 stretch: CycloneDX · PyRIT · CI scan  

---

## 8. Track B issues W2–W6 (direction)

Track B tooling is **owned by Grace/Jack** — issues below are **integration-aware**, not prescriptive on ROUGE vs judge libraries.

### W2

**Parent:** `[Track B][W2] Evaluation framework start`

| Issue | Direction |
|-------|-----------|
| `[Track B][W2] EvalRun and TaskResult schemas` | Align with docs/data-model.md; `provenance`, ops metrics |
| `[Track B][W2] Task loader` | `tasks/rubrics/it_support.yaml` |
| `[Track B][W2] Gateway runner smoke` | One model from gateway-models.md; latency/tokens |
| `[Track B][W2] MVP suite order doc` | evaluation-framework rollout table |

**Relate:** `[Team][W2] Gateway model catalog`

### W3

Multi-model runner · ROUGE-L (if summarization) · variation testing · IT support E2E · ops metrics on every call

### W4

Core suites per evaluation-framework · optional benchmark subset · unit tests · **use same 3 gateway models as Track A pilot** (comment on catalog issue)

### W5

`POST/GET /evals` · Celery eval worker · LLM-as-judge (their design) · **Relate** Team API

### W6

Efficacy charts · suite matrix · **Relate** #1 Dashboard

### Integration checklist (Track B template)

```markdown
## Integration (fill on each Track B issue)
- [ ] Uses gateway_model_id from Team catalog
- [ ] Writes EvalRun/EvalResult shape compatible with data-model.md
- [ ] Records latency_ms, tokens_in, tokens_out, cost_usd if available
- [ ] Does NOT include red-team / jailbreak prompts (Track A safety)
```

---

## 9. Team issues W2–W6

| Issue | Week | Description |
|-------|------|-------------|
| `[Team][W2] Gateway model catalog in Postgres + docs` | W2 | Seed `models` from gateway-models.md; confirm LiteLLM IDs with OIT; flag Mistral deprecated |
| `[Team][W2] Data model — deployment_context and pillar fields` | W2 | docs/data-model.md; review with A+B |
| `[Team][W2] Docker Compose` | W2 | API, worker, Redis, Postgres |
| `[Team][W2] GitLab CI` | W2 | lint, test, docker build |
| `[Team][W2] Nutrition label UI mockups` | W2 | Relate #1 |
| `[Team][W5] Postgres schema migration v1` | W5 | scans, findings, safety_*, eval_* |
| `[Team][W5] FastAPI + Celery` | W5 | queue wiring |
| `[Team][W5] GET /models and GET /models/{id}` | W5 | aggregates security + efficacy |
| `[Team][W6] Model detail three-pillar layout` | W6 | scanning, safety, efficacy sections |
| `[Team][W6] Model list status columns` | W6 | |
| `[Team][W7] Demo rehearsal` | W7 | |

---

## 10. Templates

| File | Use |
|------|-----|
| `issue_templates/Track_A_Issue.md` | Track A stories |
| `issue_templates/Track_A_Task.md` | Track A child tasks |
| `issue_templates/Track_B_Issue.md` | Track B stories |
| `issue_templates/Track_B_Task.md` | Track B child tasks |
| `issue_templates/Team_Issue.md` | Shared / integration stories |

---

**Docs index:** [`docs/README.md`](../docs/README.md) · **Weekly outcomes:** [`docs/team-tracks.md`](../docs/team-tracks.md)
