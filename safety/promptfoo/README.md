# Promptfoo

Hand-written Duke policy probes + generated red-team attacks. Run from **repo root**.

For the full pipeline (policy + Garak + merge), use [`../run_safety.sh`](../run_safety.sh). This README covers running Promptfoo on its own.

## Setup (once)

Secrets come from the repo-root `.env` (gateway token, used as `OPENAI_API_KEY`).

```bash
docker compose --env-file .env -f safety/promptfoo/docker/compose.yml build
```

## Session variables

```bash
export PF_DC="docker compose --env-file .env -f safety/promptfoo/docker/compose.yml"
export GATEWAY_MODEL="GPT 4.1 Mini"
export SLUG=gpt-4.1-mini
mkdir -p safety/promptfoo/output/${SLUG}
```

## Run policy probes

```bash
$PF_DC run --rm -e GATEWAY_MODEL="$GATEWAY_MODEL" promptfoo \
  promptfoo eval -c promptfooconfig.yaml -o output/${SLUG}/eval.json

PYTHONPATH=. uv run python safety/promptfoo/export_safety_result.py \
  safety/promptfoo/output/${SLUG}/eval.json
```

Output: `output/<slug>/safety_result.json` (`probe_suite: promptfoo_duke_policy_v1`).

Equivalent via wrapper (policy only — skips Garak and red-team):

```bash
./safety/run_safety.sh --skip-garak --skip-redteam
```

## Run red-team

Red-team generation stays local (`PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true`, set in `compose.yml`).

```bash
$PF_DC run --rm -e GATEWAY_MODEL="$GATEWAY_MODEL" -e REDTEAM_GRADER_MODEL="${REDTEAM_GRADER_MODEL:-GPT 4.1 Mini}" promptfoo \
  promptfoo redteam run -c promptfooconfig.redteam.yaml \
  -o output/${SLUG}/redteam_eval.json --delay 500 --max-concurrency 1 --force

PYTHONPATH=. uv run python safety/promptfoo/export_safety_result.py \
  safety/promptfoo/output/${SLUG}/redteam_eval.json
```

`REDTEAM_GRADER_MODEL` (default **GPT 4.1 Mini**) grades llm-rubric assertions — do **not** use the target model as its own judge. `run_safety.sh` passes this env into Docker automatically.

Azure content-policy blocks count as **pass** in export (gateway blocked the attack). See policy probe `duke.policy.004`.

Output: `output/<slug>/redteam_safety_result.json`.

Equivalent via wrapper (red-team only — skips Garak):

```bash
./safety/run_safety.sh --skip-garak
```

## Add or edit policy probes

Edit `tests:` in `promptfooconfig.yaml`. Each entry needs:

```yaml
  - description: Short title
    vars:
      probe_id: duke.policy.014
      category: policy               # smoke | policy | jailbreak | leakage
      severity: high                 # low | medium | high
      question: "User prompt here"
    assert:
      - type: icontains-any
        value: [expected, phrases]
```

Re-run **Run policy probes** (or `./safety/run_safety.sh --skip-garak --skip-redteam`).

### Current policy probes

| `probe_id` | `category` |
|------------|------------|
| `duke.smoke.001` | smoke |
| `duke.policy.001`–`009` | policy / jailbreak / leakage |
| `duke.policy.010` | leakage (FERPA) |
| `duke.policy.011` | leakage (PII) |
| `duke.policy.012` | policy (off-topic) |
| `duke.policy.013` | policy (insecure packages) |

Model: `GATEWAY_MODEL` env → `openai:chat:{{env.GATEWAY_MODEL}}` in config.

`duke.policy.004` (jailbreak): Azure content-policy block counts as **pass** in export.

## Add or edit red-team plugins

Edit `redteam.plugins` in `promptfooconfig.redteam.yaml`:

```yaml
  plugins:
    - id: policy
      numTests: 2
    - id: pii
      numTests: 2
```

Local plugins (15): `policy`, `hallucination`, `overreliance`, `excessive-agency`, `pii`, `pii:direct`, `imitation`, `harmful:privacy`, `cross-session-leak`, `rbac`, `contracts`, `harmful:intellectual-property`, `harmful:cybercrime`, `debug-access`, `intent`.

The `policy` plugin and `purpose` block cover Duke multi-channel context: FERPA, HIPAA/PHI, HR, research-confidential, financial/grants, contracts, and impersonation — not only student IT/academic integrity.

Remote-only (commented in yaml): `hijacking`, `ferpa`, `harmful:specialized-advice`.

Re-run **Run red-team** (or `./safety/run_safety.sh --skip-garak`).

## Merge after individual runs

```bash
PYTHONPATH=. uv run python -m safety.merge \
  --promptfoo safety/promptfoo/output/${SLUG}/safety_result.json \
  --promptfoo safety/promptfoo/output/${SLUG}/redteam_safety_result.json \
  -o safety/output/${SLUG}/base/merged_safety_result.json
```

Add `--garak` if you also have a Garak export. See [`../README.md`](../README.md).

## Troubleshooting

### `Failed query: update "evals" set "prompts" = ?`

Promptfoo's internal SQLite eval-history database (`PROMPTFOO_CONFIG_DIR`) was
shared across concurrent runs. Each run now uses an isolated directory:
`safety/output/<slug>/<profile>/.promptfoo`. If you see this error on an older
checkout, rebuild the promptfoo image and re-run with a current `safety/run.py`.

Concurrent safety runs for **different** models are allowed; they must not share
one `PROMPTFOO_CONFIG_DIR`.

## Files

| Path | Role |
|------|------|
| `promptfooconfig.yaml` | Policy input (14 tests) |
| `promptfooconfig.redteam.yaml` | Red-team input |
| `export_safety_result.py` | Normalizer CLI |
| `output/<slug>/eval.json` | Raw policy eval |
| `output/<slug>/safety_result.json` | Normalized export |
