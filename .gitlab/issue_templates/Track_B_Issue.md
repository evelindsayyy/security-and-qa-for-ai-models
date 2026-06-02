## User story
As **ROLE**, I want **GOAL**, so that **BENEFIT**.

## Acceptance criteria
- [ ] 

## Integration (required)
- [ ] Uses `gateway_model_id` from Team catalog ([`docs/gateway-models.md`](../docs/gateway-models.md))
- [ ] Output shape compatible with [`docs/data-model.md`](../docs/data-model.md) (`EvalRun`, `EvalResult`)
- [ ] Records latency_ms, tokens_in, tokens_out (and cost if available)
- [ ] No red-team / jailbreak / academic-dishonesty prompts (Track A **safety**)

## Tool output → data model
- [ ] Run executed; **sample JSON** attached or path in comment (`testing/eval/output/` or `evaluator/` output)
- [ ] Fields map to `eval_runs` / `eval_results` (or noted as provisional in comment)

## Out of scope
Define Track B-specific tools and metrics in issue comments — this template only enforces cross-track contracts.

## References
- docs/track-b-framework.md
- docs/data-model.md (EvalRun shape)

/label ~track-b ~efficacy
