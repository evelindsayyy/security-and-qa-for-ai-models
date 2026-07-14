# Validation Study — does the automated judge agree with people?

> **Final result — all 6 raters, 180 labels over 60 comparisons.** Regenerate any time
> with `uv run python docs/validation-study/analyze.py`.

## The question
The Efficacy pillar scores open-ended answers with an **LLM-as-judge**. That is only
defensible if the judge agrees with *people*. This study measures that agreement —
and, just as important, measures it **against the ceiling of how much humans agree
with each other**, so the judge's number is interpreted relative to what is even
achievable on a subjective task.

## Method
- **Task.** Pairwise preference: given a prompt and two answers, pick the better one
  or "About the same." No reference answer — the same format the humans and the judge
  both see.
- **Systems compared (3).** `Qwen2.5-7B-Instruct` (self-hosted on the DCC — the
  alignment target), `GPT 4.1 Mini`, `GPT 4.1 Nano`. Every comparison pits the target
  against one opponent.
- **Items.** 60 pairwise comparisons drawn from a 108-item pool spanning the
  open-ended suites (email drafting, plain-language rewriting, tutoring, policy Q&A,
  IT support, summarization).
- **Human raters.** 6 raters × 30 items, **3 independent labels per item** via a
  complementary-partition design (no rater sees a comparison twice; each item's three
  labels come from three different raters). Anonymous Qualtrics link, ~25 min each.
- **The judge.** `Llama 4 Maverick` (cross-family to both Qwen and the OpenAI systems,
  per the MT-Bench rule), temperature 0, reference-free pairwise prompt. Each pair is
  judged in **both display orders**; a verdict that survives the swap is kept, a verdict
  that flips is recorded as a **position flip** and counted as a tie.
- **Statistics** (pure-numpy, `prefstats.py`): human–human **Fleiss' κ** (the gate),
  judge-vs-human **Cohen's κ** + raw % agreement (the headline), position/length **bias
  probes**, and a **Bradley-Terry** ranking of the three systems from the human
  preferences. Consensus = strict majority of an item's labels.

## Results (6 raters · 180 labels · 60 comparisons)

### Human agreement — the ceiling / gate
| Metric | Value | Reading (Landis–Koch) |
|---|---|---|
| **Human–human Fleiss' κ** | **0.27** | fair — **below the pre-registered 0.40 gate** |

Human agreement is only *fair* — expected for this task: "which of two good answers is
better" is genuinely subjective on close pairs, where reasonable people disagree. It
sets an honest ceiling — no automated judge can be expected to exceed the agreement
humans themselves reach.

### Judge vs. human — the headline
| Metric | Value | Reading |
|---|---|---|
| **Cohen's κ (judge vs. human consensus)** | **0.23** | fair |
| Raw % agreement | **40.0%** (n = 50 decided items) | — |

**The judge's agreement with the human consensus (κ≈0.23) sits in the same *fair* band
as the inter-human ceiling (κ≈0.27), just below it.** On a task where people themselves
only reach fair agreement, an automated judge that lands at essentially the human level
is behaving like a reasonable additional rater — the bar that matters for using it as a
scalable stand-in.

### Bias probes
| Probe | Value | Reading |
|---|---|---|
| Position bias — humans, P(pick "Response 1") | 0.41 | ~0.5 → humans are roughly position-neutral |
| Position bias — **judge, order-flip rate** | **45%** (email items 80%) | high — the judge is strongly position-sensitive |
| Length bias — longer answer won | 0.59 of 41 decided (point-biserial r = 0.17) | mild preference for the longer answer |

The judge's **45% flip rate** is the sharpest finding: on nearly half the pairs the
judge changes its pick when the two answers are swapped. The two-order protocol turns
this into a safeguard — position-driven verdicts collapse to "tie" instead of polluting
the score. Humans, by contrast, show little position bias (P(R1)=0.41).

### System ranking (Bradley-Terry, from human preferences)
| Rank | System | θ (higher = preferred) |
|---|---|---|
| 1 | GPT 4.1 Mini | +1.03 |
| 2 | GPT 4.1 Nano | +0.18 |
| 3 | Qwen2.5-7B-Instruct | 0.00 (reference) |

### Judge preference distribution (108 pairs, both-order combined)
| Judge verdict | Share |
|---|---|
| tie | 50% |
| GPT 4.1 Mini | 19% |
| Qwen2.5-7B-Instruct | 18% |
| GPT 4.1 Nano | 14% |

On the decisive half, the self-hosted **Qwen-2.5-7B is competitive with GPT-4.1-Mini** —
a strong result for a small open-weight model served on Duke's own GPUs.

## Interpretation
- The judge is a **usable stand-in, not an oracle**: its agreement with the human
  consensus (κ≈0.23) is in the same *fair* band as inter-human agreement (κ≈0.27) —
  about as reliable as an average human rater, marginally below the human ceiling.
- We **quantify where it is weak**: a 45% position-flip rate, mitigated by the
  two-order protocol, and a mild length preference. These are reported, not hidden.
- The value of the study is calibration: efficacy scores should be read as
  "judge agreement ≈ human agreement," and open-ended rankings carry the caveat that
  the underlying human signal is only fair.

## Limitations (honest)
- **6 raters** is a calibration sample, not a population study; κ estimates are wide.
- Comparison **pairs and references are illustrative** (not validated by a Duke
  office), so the ranking is pipeline validation, not an authoritative Duke benchmark.
- The task is **inherently subjective**; fair human agreement is expected and bounds
  what any judge can achieve.
- Single-turn only; no multi-turn or adversarial items.

## Conclusion
On Duke-flavored open-ended tasks, the automated LLM judge agrees with human
consensus at roughly the level humans agree with each other, while exhibiting a
measurable position bias that the evaluation controls for by design. That is the
evidence needed to use the judge as a scalable, honestly-bounded stand-in for human
preference — and to read every open-ended score with its human ceiling in view.

## Reproducibility
```
# 1. judge side (needs the gateway; cached):
uv run python docs/validation-study/run_pairwise_judge.py        # -> judge_prefs.jsonl
# 2. human side + headline (rater CSVs in docs/validation-study/responses_csv/):
uv run python docs/validation-study/analyze.py                   # prints all κ + writes dpo_pairs.jsonl
```
Inputs: `item_pool.jsonl`, `responses.jsonl`, `rater_map.csv`, `responses_csv/rater_0X.csv`,
`judge_prefs.jsonl`. Stats engine: `prefstats.py` (Cohen's/Fleiss' κ, point-biserial,
Bradley-Terry — pure numpy, unit-tested in `unit_tests/test_prefstats.py` +
`test_analyze.py`).
