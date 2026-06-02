# GitLab

**Technical overview:** [`docs/`](../docs/).

---

## Tracks

| Track | Members | Prefix | Label |
|-------|---------|--------|-------|
| A | Raphael, Nithi | `[Track A]` | `track-a` |
| B | Grace, Jack | `[Track B]` | `track-b` |
| Team | Everyone | `[Team]` | `team-shared` |

Labels: `scanning` · `safety` · `gateway` · `efficacy` · `evaluator` · `frontend` · `mvp` · `spike` · `docs` · …

---

## Milestones

| Milestone | Status / goal |
|-----------|----------------|
| W1–W2 | **Closed** — spikes, docs |
| **W3** | **Current** — packages, catalog, CI, frontend, MVP efficacy on 1 gateway model |
| W4 | E2E scan; safety + MVP efficacy on 3 gateway models |
| W5 | Flask `api/`, Postgres, Celery |
| W6–W7 | Full UI, demo freeze |

---

## Spikes → packages → Postgres

Spikes in `testing/` exist to **run tools and inspect output**, not to ship production code.

| Step | What to prove |
|------|----------------|
| 1. Spike | Run ModelScan, garak, promptfoo, eval scripts; save **raw + normalized JSON** samples |
| 2. Map | Align fields to [`docs/data-model.md`](../docs/data-model.md); note gaps in the issue comment |
| 3. Package | `scanner/`, `safety/`, `evaluator/` Pydantic schemas + on-disk JSON (W3–4) |
| 4. API | Week 5 migrations + `api/` persistence |

Use label `spike` when the issue is mainly “see what the tool returns.” Parent `mvp` issues should link the spike MR or sample files.

---

## Hygiene

1. New issue → `issue_templates/`
2. Assign **current** milestone (W3 now)
3. Child tasks when work splits; MR uses `Closes #N`
4. Monday: open issues for **that week only** (parent first, then its children in order)

| Doc | Use |
|-----|-----|
| [`docs/team-tracks.md`](../docs/team-tracks.md) | Weekly outcomes |
| [`docs/track-a-framework.md`](../docs/track-a-framework.md) | Security |
| [`docs/track-b-framework.md`](../docs/track-b-framework.md) | Efficacy / MVP suites |
| [`docs/gateway-models.md`](../docs/gateway-models.md) | Catalog |
| [`docs/data-model.md`](../docs/data-model.md) | Postgres sketch |
