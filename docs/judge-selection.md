# Judge selection — interim decision (week 4)

**Status: INTERIM.** Based on cross-judge experiments run weeks 3–4. The
weeks 7–8 validation study (human raters, Pearson + Cohen's Kappa per
dimension) is the final arbiter; this document records what we use until
then and why. Reproduce all numbers with:

```bash
cd evaluator && python compare_judges.py --from-results --suite it_support_v1
```

## Decision

| Role | Model | Notes |
|---|---|---|
| **Primary judge** (all suites) | **Llama 4 Maverick** | temperature 0, `reference_based_v2` prompt |
| Secondary / strict spot-check | gpt-oss-120b | requires `--judge-max-tokens 2000` (reasoning model) |
| Dropped from pool | Llama 3.3 | leniency ceiling — adds no information |
| Available (optional) | GPT 4.1 Mini, gpt-5-chat | re-enabled 2026-06-22 — see Update below |

## Update — OpenAI judges re-enabled (2026-06-22)

Triggered by reconsideration item #3 (new judge-capable Gateway models). The
gateway `metadata`/`store` 400 that had blocked all OpenAI models was fixed
gateway-side; `GPT 4.1 Mini` and `gpt-5-chat` were verified to return valid
judge JSON via our SDK path (the bar `gpt-oss-120b` fails ~75% of the time),
and both are non-reasoning chat models (no hidden-thinking-token risk). Both are
now in the launcher allowlist (`frontend/eval_launch.py`).

- **Data handling — approved.** Mentor sign-off (2026-06-22): OpenAI judges are
  acceptable **as long as the model is accessed through the Duke Gateway** (not
  the direct OpenAI API). This is already how the pipeline works — every call
  goes through `litellm.oit.duke.edu`, so eval data is covered by the Gateway's
  agreement (which routes OpenAI via Azure OpenAI).
- **Still options, not the new primary.** Maverick stays the documented primary
  judge until the weeks 7–8 human-validation study decides primacy; these are
  available for cross-judge comparison and for users who want a stronger grader.
- **Cross-family rule still applies.** An OpenAI judge must not score an OpenAI
  candidate (self-preference). `model_family()` now treats Qwen as its own
  family, so an OpenAI judge *is* allowed to score a self-hosted Qwen candidate.

## The evidence

### Experiment 1 — same answers, three judges (it_support, gpt-5-chat, Wednesday)

Byte-identical candidate responses scored by all three judges:

| Judge | Overall | Completeness | Coverage |
|---|---|---|---|
| Llama 3.3 | 5.00 | 5.00 | 12/12 |
| Llama 4 Maverick | 4.90 | 4.83 | 12/12 |
| gpt-oss-120b | 4.63 | 4.00 | 12/12 |

0.37 spread on identical answers. Llama 3.3 awarded perfect scores on every
dimension of every question — a judge that never disagrees cannot inform.

### Experiment 2 — same judges, weak candidate (it_support, Llama 4 Scout, Thursday)

| Judge | gpt-5-chat | Llama 4 Scout | Discrimination (gap) |
|---|---|---|---|
| Llama 3.3 | 5.00 | 4.23 | 0.77 |
| **Llama 4 Maverick** | 4.90 | **3.91** | **0.99** |
| gpt-oss-120b | 4.63 | 4.18 | 0.45 |

Three findings:

1. **Rankings are judge-invariant: 100% rank concordance across all judge
   pairs.** Every judge orders gpt-5-chat > Scout. Judge choice changes the
   numbers, not the conclusions — the key robustness result for the
   dashboard.
2. **Maverick is the best discriminator** (0.99 gap between strong and weak
   candidate). gpt-oss-120b is strict at the top but compresses at the
   bottom (0.45) — it treats strong and weak answers more alike, which is
   the opposite of what a useful judge does.
3. **No self-preference bias detected for Maverick.** MT-Bench predicts
   judges favor their own family; Maverick scored its family-mate Scout
   *lowest* of the three judges (3.91 vs 4.18/4.23). The measured bias
   direction is against the rule's prediction.

### Experiment 3 — policy_qa_v1.1 pilot (Thursday, Maverick judging)

| Candidate | Overall | citation_precision | contextualization |
|---|---|---|---|
| gpt-5-chat | 4.33 | 2.83 | 4.83 |
| GPT 4.1 Mini | 3.74 | 2.00 | 3.50 |
| Llama 4 Scout | 3.31 | 1.67 | 2.83 |

Discrimination 1.02 across three candidates with no ceiling effect;
citation_precision is the active dimension exactly as the rubric design
intended. Maverick produces usable signal on the new suite unmodified.

## On the cross-family rule (MT-Bench)

The rule says judge family ≠ candidate family. Our position:

- **The launcher form keeps enforcing it** — it's the right conservative
  default for users who haven't read this document.
- **CLI methodology runs may pair Maverick with Llama candidates** because
  (a) the empirically measured bias direction is *against* its own family,
  and (b) rankings are judge-invariant anyway (Experiment 2), so no
  conclusion rests on the pairing.
- For any **headline number on a Llama-family candidate**, run the
  gpt-oss-120b spot-check (`--judge-max-tokens 2000`) alongside and report
  both if they disagree on more than magnitude.

## Known history / caveats

- Week-3 baseline rows were judged with `reference_based_v1` (hardcoded
  IT-support dims); weeks 4+ use `reference_based_v2` (rubric-aware).
  `judge_prompt_version` in each row disambiguates.
- gpt-oss-120b initially failed 9/12 judgments by exhausting its 600-token
  budget on hidden reasoning — fixed via `--judge-max-tokens`. Its strict
  completeness scores cite real reference omissions (verified by reading
  rationales), so strictness is calibration, not noise.
- All scores still rest on PLACEHOLDER references (OIT/policy-office
  validation is week 5); judge comparisons are methodology validation, not
  authoritative model quality claims.

## Reconsideration triggers

1. The weeks 7–8 human validation study (decides which judge tracks human
   raters — overrides everything here).
2. Any future cross-judge run showing rank concordance < 100% on ≥3 shared
   candidates.
3. New judge-capable models on the Gateway allowlist.
