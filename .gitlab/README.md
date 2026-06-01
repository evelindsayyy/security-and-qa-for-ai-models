# GitLab — how we track work

**Technical docs:** [`docs/`](../docs/) (architecture, tools, frameworks).  
---

## Tracks

| Track | Members | Title prefix | Label |
|-------|---------|--------------|-------|
| A — Scanning & Safety | Raphael, Nithi | `[Track A]` | `track-a` |
| B — Evaluation | Grace, Jack | `[Track B]` | `track-b` |
| Team — shared | Everyone | `[Team]` | `team-shared` |

---

## Labels

`track-a` · `track-b` · `team-shared` · `scanning` · `safety` · `red-team` · `gateway` · `efficacy` · `evaluator` · `frontend` · `mvp` · `spike` · `docs` · `blocked` · `stretch`

- `gateway` — Duke AI Gateway model IDs (not HF DGX scan)
- `scanning` — HF artifact pipeline only

---

## Milestones (names only)

| Milestone | One-line goal |
|-----------|----------------|
| W1 — Kickoff | Scaffold, gateway test, tool research |
| W2 — Foundation | Spikes, schemas, catalog (mostly done) |
| W3 — Core pipelines | Packages + structured JSON; W2 carryover |
| W4 — E2E & tests | Scan E2E; safety on 3 gateway models |
| W5 — API & integration | Flask, Postgres, Celery, `/scans` `/safety` `/evals` |
| W3+ — Frontend | `frontend/` — model list, mockups |
| W6 — Frontend | Full nutrition label UI |
| W7 — MVP demo (freeze) | Full gateway catalog |
| W8–W9 — Hardening & handoff | FP study, runbooks |
| W10 — Stretch | Optional |

Full milestone descriptions to paste: `gitlab-transfer.md` → Milestones section.

---

## Creating work items

1. **New issue** — pick template under `issue_templates/` (Track A, Track B, Team, or Task).
2. **Parent issue** — story for the week; assign milestone; add labels.
3. **Child tasks** — use `Track_*_Task.md`; set parent link `#PARENT_ID`.
4. **Integration (W5–W6)** — relate Track A, Track B, and Team API/frontend issues.
5. **Merge request** — `Closes #N` in description when done.

### Adding a new week

- Create issues only for that week’s milestone (avoid backlog dumping).
- Monday: add next week’s issues from `gitlab-transfer.md`.
- Amend milestones in GitLab if scope shifts; note in milestone description.

---

## References

| Doc | Use |
|-----|-----|
| [`docs/team-tracks.md`](../docs/team-tracks.md) | Weekly outcomes |
| [`docs/track-a-framework.md`](../docs/track-a-framework.md) | Scanning + safety |
| [`docs/track-b-framework.md`](../docs/track-b-framework.md) | Efficacy |
| [`docs/gateway-models.md`](../docs/gateway-models.md) | Model catalog |
| [`docs/data-model.md`](../docs/data-model.md) | Postgres / JSON shapes |

**Templates:** `issue_templates/Track_A_Issue.md`, `Track_B_Issue.md`, `Team_Issue.md`, `Track_*_Task.md`
