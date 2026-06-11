# Safety (Track A — inference / red team)

Gateway red team via Garak, Promptfoo, and Duke policy probes.

Track A safety artifacts follow [`docs/data-model.md`](../docs/data-model.md):
each JSON file has one `run` block for `safety_runs` and a `findings` list
for `safety_findings`.

Garak and Promptfoo are intentionally scored separately because they measure
different units:

- Garak probes model behavior across vulnerability families and detector hits.
- Promptfoo evaluates concrete contextual tests/assertions and pass/fail rows.

## Pipeline

- `safety/__main__.py` — CLI entry point for `python -m safety scan <model_id>`
- `safety/pipeline.py` — orchestration layer that resolves a target and runs the tool wrappers
- `safety/targets.py` — model/provider registry to avoid one-off YAML per target
- `safety/garak_runner.py` and `safety/promptfoo_runner.py` — tool-specific runners
- `safety/safety_score.py` — tool-specific scorers that write Track A result JSON
- `safety/schemas.py` — `SafetyResult`, `SafetyRun`, and `SafetyFinding` contracts
- `safety/templates/` — reusable config templates that keep test logic separate from runtime targets

The runtime target is injected from the registry instead of being hard-coded
into every YAML file. `targets.py` resolves exact Duke AI Gateway model ids,
common aliases such as `gpt-4.1-mini` and `llama-4-maverick`, and the live
`GET /v1/models` catalog when Gateway credentials are available.

## Output layout

`python -m safety scan gpt-4.1-mini` writes separate tool outputs:

```text
safety/output/gpt-4.1-mini/
  pipeline_summary.json
  garak/
    garak_runtime.yaml
    raw_garak_report.json
    garak_run_metadata.json
    garak_safety_result.json
  promptfoo/
    promptfoo_runtime.yaml
    raw_promptfoo_report.json
    promptfoo_run_metadata.json
    promptfoo_safety_result.json
```

`garak_safety_result.json` uses `probe_suite: garak_subset_v1` and findings
with `source: garak`.

`promptfoo_safety_result.json` uses `probe_suite:
promptfoo_duke_policy_v1` and findings with `source: promptfoo`.

Both result files use:

```json
{
  "schema_version": "safety_result_v1",
  "run": {
    "id": "...",
    "gateway_model_id": "gpt-4.1-mini",
    "status": "complete",
    "deployment_context": {},
    "probe_suite": "garak_subset_v1",
    "summary_pass_rate": 0.85,
    "tool_results": {},
    "started_at": "...",
    "completed_at": "..."
  },
  "findings": []
}
```

## Commands

Run both tools and score whichever raw outputs are available:

```bash
python -m safety scan gpt-4.1-mini
python -m safety scan "Llama 4 Maverick"
python -m safety scan gpt-5-chat
```

Score existing reports directly:

```bash
python -m safety score-garak \
  --input safety/output/gpt-4.1-mini/garak/raw_garak_report.json \
  --output safety/output/gpt-4.1-mini/garak/garak_safety_result.json \
  --model-id gpt-4.1-mini

python -m safety score-promptfoo \
  --input safety/output/gpt-4.1-mini/promptfoo/raw_promptfoo_report.json \
  --output safety/output/gpt-4.1-mini/promptfoo/promptfoo_safety_result.json \
  --model-id gpt-4.1-mini
```
