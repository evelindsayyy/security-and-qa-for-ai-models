# GitHub Project Operations

This directory contains the issue forms and GitHub Actions workflow used to run the project on GitHub.

## 1. Work Tracking

Use the Track A, Track B, or Team issue form when creating work. Preserve the existing labels and milestones during the GitLab metadata import so historical links remain understandable.

---

## 2. Continuous Integration

The [`ci.yml`](workflows/ci.yml) workflow runs Ruff, Python unit tests, the frontend build, and Vitest for every pull request and push. A successful `main` build publishes the web image to GitHub Container Registry.

---

## 3. Production Deployment

Run the CI workflow from the Actions tab with `deploy` enabled to deploy a selected `main` commit. Set the `DEPLOY_AUTO` repository variable to `true` only when every successful push to `main` should deploy automatically.

Create a protected `production` environment and configure these environment secrets:

| Secret | Value |
|--------|-------|
| `DEPLOY_SSH_PRIVATE_KEY` | Private SSH key authorized for the application VM deploy account |
| `DEPLOY_SSH_KNOWN_HOSTS` | Verified `known_hosts` entry for the application VM |
| `DEPLOY_USER` | SSH deployment user, normally `security-qa-deploy` |
| `DEPLOY_HOST` | Application VM hostname |
| `DEPLOY_PATH` | Absolute repository path on the application VM |

The optional `BUILD_PILLARS` repository variable controls whether deployment rebuilds the pillar images. Set it to `1` when those images must be refreshed.

---

## 4. Branch Protection

Protect `main` after the first successful workflow run. Require the lint, unit test, and frontend build checks, block force pushes, and require pull requests for routine changes.
