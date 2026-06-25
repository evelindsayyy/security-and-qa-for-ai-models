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
| **W3** | **Closed** — packages, catalog, frontend, MVP efficacy |
| **W4** | **Closed** — E2E scan/safety/eval; CI on shared runners (Jun 17) |
| **W5** | **Closed** — Postgres loaders (partial carry to W6) |
| **W6** | **Current** — full `api/`, demo-ready UI |
| W7+ | Demo freeze, polish |

---

## CI (shared runners)

GitLab jobs run on Duke **shared runners** (`docker+machine`).

1. Pipeline: **lint** (ruff) → **unit-tests** (~380).
2. On **`main`**: Buildah builds `docker/Dockerfile` → GitLab container registry (`web:${CI_COMMIT_SHORT_SHA}`).
3. **`deploy`** — default **manual** on `main` (click Play after `build-web-image`). Set CI/CD variable **`DEPLOY_AUTO=true`** for automatic deploy.

Config: [`.gitlab-ci.yml`](../.gitlab-ci.yml). Detail: [`docs/docker.md`](../docs/docker.md).

### Deploy CI/CD variables

Set in **Settings → CI/CD → Variables** (maintainers):

| Variable | Type | Example |
|----------|------|---------|
| `DEPLOY_SSH_PRIVATE_KEY` | File, masked | Private key whose public half is in `security-qa-deploy`’s `~/.ssh/authorized_keys` on the VM |
| `DEPLOY_SSH_KNOWN_HOSTS` | File | Output of `ssh-keyscan model-advisor.colab.duke.edu` |
| `DEPLOY_USER` | Variable | `security-qa-deploy` |
| `DEPLOY_HOST` | Variable | `model-advisor.colab.duke.edu` |
| `DEPLOY_PATH` | Variable | `/home/vcm/security-and-qa-for-ai-models` (repo clone path; deploy user must be able to `git pull` there) |
| `DEPLOY_AUTO` | Variable (optional) | `true` — deploy automatically on every `main` pipeline (default: manual) |
| `BUILD_PILLARS` | Variable (optional) | `1` to rebuild pillar images on deploy |

**VM prerequisites:** git clone + deploy key, `.env`, Docker, one-time `./docker/build-pillars.sh`. The web container bind-mounts the repo; deploy pulls the CI-built image for Python deps and runs `git pull` for app code.

---

## Spikes → packages → Postgres

Spikes in `testing/` exist to **run tools and inspect output**, not to ship production code.

| Step | What to prove |
|------|----------------|
| 1. Spike | Run ModelScan, garak, promptfoo, eval scripts; save **raw + normalized JSON** samples |
| 2. Map | Align fields to [`docs/data-model.md`](../docs/data-model.md); note gaps in the issue comment |
| 3. Package | `scanner/`, `safety/`, `evaluator/`, `benchmarks/` schemas + artifacts |
| 4. Postgres | `*/db/` loaders, `api.ingest`, UI `*_db_data.py` |
| 5. API | REST GET/POST for all pillars (eval GET live) |

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
