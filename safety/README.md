# Safety (Track A — inference / red team)

Gateway red team via garak, promptfoo, and Duke policy probes → `SafetyResult`.

Gateway red team (garak, promptfoo, Duke probes). Week 3+ package. [`docs/track-a-framework.md`](../docs/track-a-framework.md). Tasks: [`.gitlab/README.md`](../.gitlab/README.md).

## New pipeline scaffold

The safety area now has an initial scanner-style pipeline scaffold:

- `safety/__main__.py` — CLI entry point for `python -m safety scan <model_id>`
- `safety/pipeline.py` — orchestration layer that resolves a target and runs the tool wrappers
- `safety/targets.py` — model/provider registry to avoid one-off YAML per target
- `safety/garak_runner.py` and `safety/promptfoo_runner.py` — tool-specific runners
- `safety/templates/` — reusable config templates that keep test logic separate from runtime targets

The runtime target is injected from the registry instead of being hard-coded into every YAML file, which is the first step toward a reusable red-teaming pipeline in the safety directory.
