# Garak

Automated probes against Duke AI Gateway. Run from **repo root**. Maps to `probe_suite: garak_subset_v1` ([`docs/data-model.md`](../../docs/data-model.md)).

## Files

| Path | Role |
|------|------|
| `garak_gpt41mini_low_guardrail.yaml` | **Input** — model, probes, caps |
| `export_safety_result.py` | Report JSONL → `output/safety_result.json` |
| `output/garak-gpt41mini-low-guardrail.report.jsonl` | Raw scan |
| `output/safety_result.json` | Normalized (`SafetyRunResult`) |

## Setup

```bash
cp safety/garak/docker/.env.example safety/garak/docker/.env
# set OPENAICOMPATIBLE_API_KEY (= DUKE_GATEWAY_KEY)

docker compose --env-file safety/garak/docker/.env \
  -f safety/garak/docker/compose.yml build

export DC="docker compose --env-file safety/garak/docker/.env -f safety/garak/docker/compose.yml"
```

## 1. Run

```bash
$DC run --rm garak python -m garak --config garak_gpt41mini_low_guardrail.yaml
```

Writes `output/garak-gpt41mini-low-guardrail.report.jsonl` (+ `.html`). First run ~15–25 min.

## 2. Export

```bash
$DC run --rm garak python3 export_safety_result.py
# or: python3 safety/garak/export_safety_result.py safety/garak/output/garak-gpt41mini-low-guardrail.report.jsonl
```

## Changing probes

Edit `garak_gpt41mini_low_guardrail.yaml`:

| Field | What it does |
|-------|----------------|
| `plugins.probe_spec` | Comma-separated garak modules (e.g. `misleading,snowball`) |
| `plugins.target_name` | LiteLLM model id (`GPT 4.1 Mini`) |
| `run.soft_probe_prompt_cap` | Max prompts per probe (misleading ignores cap) |
| `run.generations` | Completions per prompt |
| `reporting.report_prefix` | Output filename prefix |

Output `probe_id` values: `garak.<module>` (one finding per module). Listed in `safety_result.json` → `tool_results.garak.probe_ids`.

Avoid high-filter probes (jailbreak, toxicity) until OIT approves — see YAML header comments.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No detectors, nothing to do` | Use stock `compose.yml` (no `user:` override) |
| Root-owned `output/` | `chown -R "$(id -u):$(id -g)" safety/garak/output` or `$DC run --rm garak sh -c 'chown -R 1000:1000 output'` |

Merge: [`../README.md`](../README.md).
