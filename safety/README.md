# Safety (Track A — inference / red team)

Gateway red team via garak, promptfoo, and Duke policy probes → `SafetyResult` JSON aligned with [`docs/data-model.md`](../docs/data-model.md).

| Tool | Directory | `probe_suite` |
|------|-----------|---------------|
| Promptfoo (policy + red-team) | [`promptfoo_testing/`](promptfoo_testing/README.md) | `promptfoo_duke_policy_v1` |
| Garak (automated probes) | [`garak_testing/`](garak_testing/README.md) | `garak_subset_v1` |

Week 3 spike: run both against **GPT 4.1 Mini**. Promptfoo smoke → `output/smoke_safety_result.json`; garak → `output/safety_result.json`. Then lock Pydantic types in `safety/schemas.py`. Framework: [`docs/track-a-framework.md`](../docs/track-a-framework.md).
