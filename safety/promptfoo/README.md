# Promptfoo

Duke policy probes against AI Gateway. Run from **repo root**. Maps to `probe_suite: promptfoo_duke_policy_v1` ([`docs/data-model.md`](../../docs/data-model.md)).

## Files

| Path | Role |
|------|------|
| `promptfooconfig.yaml` | **Input** — 10 Duke probes |
| `promptfooconfig.redteam.yaml` | **Input** — red-team plugins |
| `export_safety_result.py` | `eval.json` → `output/safety_result.json` |
| `output/eval.json` | Raw eval |
| `output/redteam_eval.json` | Raw red-team eval |
| `output/safety_result.json` | Normalized policy export (`SafetyRunResult`) |
| `output/redteam_safety_result.json` | Normalized red-team export |

`-c` = YAML config only. Never `promptfoo eval -c output/*.json`.

## Setup

```bash
cp safety/promptfoo/docker/.env.example safety/promptfoo/docker/.env
# set OPENAI_API_KEY (= DUKE_GATEWAY_KEY)

docker compose --env-file safety/promptfoo/docker/.env \
  -f safety/promptfoo/docker/compose.yml build

export DC="docker compose --env-file safety/promptfoo/docker/.env -f safety/promptfoo/docker/compose.yml"
```

## 1. Policy eval

```bash
$DC run --rm promptfoo promptfoo eval -c promptfooconfig.yaml -o output/eval.json
```

## 1b. Export

```bash
$DC run --rm promptfoo python3 export_safety_result.py output/eval.json
```

## 2. Red-team (optional)

Needs `PROMPTFOO_DISABLE_REDTEAM_REMOTE_GENERATION=true` in `docker/.env`.

```bash
$DC run --rm promptfoo promptfoo redteam run \
  -c promptfooconfig.redteam.yaml -o output/redteam_eval.json \
  --delay 500 --max-concurrency 1 --force
```

## 2b. Export red-team

```bash
$DC run --rm promptfoo python3 export_safety_result.py output/redteam_eval.json
# writes output/redteam_safety_result.json (auto-detects red-team suite)
```

Probe ids: `promptfoo.redteam.<plugin>.<nnn>` (e.g. `promptfoo.redteam.hallucination.002`).

## 3. View (optional)

```bash
$DC run --rm --service-ports promptfoo promptfoo view -p 15500
```

## Changing probes

Edit `tests:` in `promptfooconfig.yaml`. Each case needs:

```yaml
  - description: Human-readable title
    vars:
      probe_id: duke.policy.003    # safety_findings.probe_id
      category: policy             # smoke | policy | jailbreak | leakage
      severity: high
      question: "User prompt here"
    assert:
      - type: ...
```

| Field | Location | Maps to |
|-------|----------|---------|
| Model | `providers[].id` | `openai:chat:GPT 4.1 Mini` ([`gateway-models.md`](../../docs/gateway-models.md)) |
| `probe_id` | `tests[].vars` | `safety_findings.probe_id` |
| `category` / `severity` | `tests[].vars` | `safety_findings` columns |

Probe list appears in export: `tool_results.promptfoo.probe_ids`.

`duke.policy.004` (jailbreak): Azure block counts as **pass** in export.

## Default probes

| `probe_id` | `category` |
|------------|------------|
| `duke.smoke.001` | smoke |
| `duke.policy.001` | policy |
| `duke.policy.002` | leakage |
| `duke.policy.003` | policy |
| `duke.policy.004` | jailbreak |
| `duke.policy.005` | policy (phishing) |
| `duke.policy.006` | policy (MFA/Duo) |
| `duke.policy.007` | policy (VPN) |
| `duke.policy.008` | policy (harmful use) |
| `duke.policy.009` | policy (Duke contact accuracy) |

Merge: [`../README.md`](../README.md).
