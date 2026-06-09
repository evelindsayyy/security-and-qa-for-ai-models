# Safety (Track A — gateway red team)

Garak + Promptfoo → [`SafetyRunResult`](schemas.py) JSON per tool → [`MergedSafetyResult`](schemas.py) via [`safety_scorer.py`](safety_scorer.py). Shapes match [`docs/data-model.md`](../docs/data-model.md) (`safety_runs`, `safety_findings`). Framework: [`docs/track-a-framework.md`](../docs/track-a-framework.md).

```text
safety/promptfoo/   promptfooconfig.yaml  →  output/eval.json  →  output/safety_result.json
safety/garak/       garak_*.yaml          →  output/*.report.jsonl  →  output/safety_result.json
safety/merge.py     both safety_result.json  →  safety/output/<model>/merged_safety_result.json
```

## Layout

| Path | Role |
|------|------|
| [`schemas.py`](schemas.py) | Pydantic types |
| [`safety_scorer.py`](safety_scorer.py) | Merge policy (like `scanner/risk_scorer.py`) |
| [`merge.py`](merge.py) | `python -m safety.merge` |
| [`exporters/`](exporters/) | Tool JSON → `SafetyRunResult` |
| [`promptfoo/`](promptfoo/README.md) | Duke policy probes (Promptfoo) |
| [`garak/`](garak/README.md) | Automated probe modules (Garak) |
| [`output/`](output/README.md) | Merged labels per `gateway_model_id` |

## Probe suites

| `probe_suite` | Tool | Config | Default probes |
|---------------|------|--------|----------------|
| `promptfoo_duke_policy_v1` | Promptfoo | `promptfoo/promptfooconfig.yaml` | `duke.smoke.001`, `duke.policy.001`–`009` |
| `promptfoo_duke_redteam_v1` | Promptfoo | `promptfoo/promptfooconfig.redteam.yaml` | `promptfoo.redteam.<plugin>.<nnn>` (12 tests default) |
| `garak_subset_v1` | Garak | `garak/garak_gpt41mini_low_guardrail.yaml` | `garak.misleading`, `garak.packagehallucination`, `garak.snowball` |

Exported JSON lists probes in `tool_results.*.probe_ids` and merged `runs[].probe_ids`.

## Changing probes

**Garak** — edit one line in `garak/garak_gpt41mini_low_guardrail.yaml`:

```yaml
plugins:
  probe_spec: misleading,packagehallucination,snowball   # comma-separated module names
```

See [Garak probe docs](https://docs.garak.ai/). Re-run scan + export; findings use `probe_id: garak.<module>`.

**Promptfoo** — edit `tests:` in `promptfoo/promptfooconfig.yaml` (add/remove cases). Each test **must** set:

```yaml
vars:
  probe_id: duke.policy.005      # → safety_findings.probe_id
  category: policy               # policy | jailbreak | leakage | smoke
  severity: medium               # low | medium | high
  question: "..."
```

Red-team plugins: `promptfooconfig.redteam.yaml` (`redteam.plugins`). Export: `redteam_eval.json` → `redteam_safety_result.json`.

**Expanding beyond 5 Duke probes:** add rows to `promptfoo/promptfooconfig.yaml` (`tests[]`). No new tool required — aim for ~10–20 ITSO-aligned cases per deployment context (credentials, FERPA, academic integrity, jailbreak, Duke-specific services). Red-team adds breadth via generated attacks; garak adds automated modules. Track B efficacy (`evaluator/`) covers task quality, not red-team — see [`docs/track-a-framework.md`](../docs/track-a-framework.md).

## Pass rate

| Level | Formula |
|-------|---------|
| Per tool | `passed findings / total findings` in that `safety_result.json` |
| Garak | One finding per **probe module** (not per attempt) |
| Merged | All findings across suites; `safety_tier` = worst failed severity |

## Merge (after both tools)

```bash
uv run python -m safety.merge \
  --promptfoo safety/promptfoo/output/safety_result.json \
  --promptfoo safety/promptfoo/output/redteam_safety_result.json \
  --garak safety/garak/output/safety_result.json \
  -o safety/output/gpt-4.1-mini/merged_safety_result.json
```

Runbooks: [`promptfoo/README.md`](promptfoo/README.md), [`garak/README.md`](garak/README.md).
