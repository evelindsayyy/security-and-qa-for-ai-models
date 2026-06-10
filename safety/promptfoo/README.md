# Promptfoo

Hand-written Duke policy probes + generated red-team attacks. Run from **repo root**.

For the full pipeline (policy + Garak + merge), use [`../run_safety.sh`](../run_safety.sh). This README covers running Promptfoo on its own.

## Setup (once)

```bash
cp safety/promptfoo/docker/.env.example safety/promptfoo/docker/.env
# OPENAI_API_KEY, GATEWAY_MODEL

docker compose --env-file safety/promptfoo/docker/.env \
  -f safety/promptfoo/docker/compose.yml build
```

## Session variables

```bash
export PF_DC="docker compose --env-file safety/promptfoo/docker/.env -f safety/promptfoo/docker/compose.yml"
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

Equivalent via wrapper:

```bash
./safety/run_safety.sh "$GATEWAY_MODEL" --skip-garak
```

## Run red-team

Requires `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true` in `docker/.env`.

```bash
$PF_DC run --rm -e GATEWAY_MODEL="$GATEWAY_MODEL" promptfoo \
  promptfoo redteam run -c promptfooconfig.redteam.yaml \
  -o output/${SLUG}/redteam_eval.json --delay 500 --max-concurrency 1 --force

PYTHONPATH=. uv run python safety/promptfoo/export_safety_result.py \
  safety/promptfoo/output/${SLUG}/redteam_eval.json
```

Output: `output/<slug>/redteam_safety_result.json`.

Equivalent via wrapper:

```bash
./safety/run_safety.sh "$GATEWAY_MODEL" --redteam --skip-garak
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

Re-run **Run policy probes** (or `./safety/run_safety.sh --skip-garak`).

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

Local plugins: `policy`, `hallucination`, `overreliance`, `excessive-agency`, `pii`, `pii:direct`, `imitation`, `harmful:specialized-advice`.

Remote-only (commented in yaml): `hijacking`, `ferpa`.

Re-run **Run red-team** (or `./safety/run_safety.sh --redteam --skip-garak`).

## Merge after individual runs

```bash
PYTHONPATH=. uv run python -m safety.merge \
  --promptfoo safety/promptfoo/output/${SLUG}/safety_result.json \
  --promptfoo safety/promptfoo/output/${SLUG}/redteam_safety_result.json \
  -o safety/output/${SLUG}/merged_safety_result.json
```

Add `--garak` if you also have a Garak export. See [`../README.md`](../README.md).

## Files

| Path | Role |
|------|------|
| `promptfooconfig.yaml` | Policy input (14 tests) |
| `promptfooconfig.redteam.yaml` | Red-team input |
| `export_safety_result.py` | Normalizer CLI |
| `output/<slug>/eval.json` | Raw policy eval |
| `output/<slug>/safety_result.json` | Normalized export |
