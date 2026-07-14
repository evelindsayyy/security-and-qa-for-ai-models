# Analysis plan — the numbers this study produces

> The exact computations, library calls, and interpretation thresholds. Code is
> the W8 spec — `scikit-learn`, `statsmodels`, `choix`, `scipy` are **not
> installed yet** (add them in a study-local requirements, kept out of the main
> pyproject to avoid the pillar dep conflict). Every step has a tiny synthetic
> self-test so the math is verified before any real data arrives.

## Input (CSV exported from the survey, joined to `version_map.csv`)

| rater_id | version | item_id | choice | response1_system | task_type |
|---|---|---|---|---|---|
| r07 | 02 | itm-001 | R1 | X | email |
| r09 | 02 | itm-015 | R2 | Y | it_support |

`choice ∈ {R1, R2, tie}`. **First, undo the display order** so a label is about
the *system*, not the position:

```python
def to_system_pref(choice, response1_system):
    if choice == "tie":
        return "tie"
    other = "Y" if response1_system == "X" else "X"
    return response1_system if choice == "R1" else other
# -> each row now has human_pref ∈ {"X", "Y", "tie"}
```

## Step A — Human consensus per item (+ tie rule)

```python
from collections import Counter
def consensus(prefs):                      # prefs = the 3 human_pref for one item
    top, n = Counter(prefs).most_common(1)[0]
    return top if n >= 2 else "no_consensus"   # 2/3 majority; else excluded, but counted
```
Report the count of `no_consensus` items — high disagreement is itself a finding.

## Step B — Human–human agreement (THE GATE — run this first)

The ceiling. If humans don't agree with each other, the rubric/instructions are
ambiguous — **fix them before trusting any judge number.**

```python
# Fleiss needs equal ratings/item -> compute PER TEAM (a team's items share its size);
# for the pooled set (team sizes vary 3-5), use Krippendorff's alpha instead.
from statsmodels.stats.inter_rater import aggregate_raters, fleiss_kappa
table, cats = aggregate_raters(rotating_label_matrix)   # items x raters -> counts
kappa_rotating = fleiss_kappa(table)

# Pooled set with varying raters/item -> Krippendorff's alpha (handles unequal n + missing)
import krippendorff
alpha_human = krippendorff.alpha(reliability_data=coded_matrix, level_of_measurement="nominal")
```

Interpretation (Landis–Koch): `<0` poor · `.01–.20` slight · `.21–.40` fair ·
`.41–.60` moderate · `.61–.80` substantial · `.81–1` almost perfect.
**Gate:** proceed only if human agreement is at least *moderate* (≳ 0.40);
otherwise revise the annotation guidelines and re-collect.

## Step C — Judge vs human agreement (the headline)

Run the judge in pairwise mode on the same pairs → `judge_pref ∈ {X,Y,tie}` per
item. Compare to the human consensus over items that have one:

```python
from sklearn.metrics import cohen_kappa_score
mask   = [c != "no_consensus" for c in human_consensus]
kappa  = cohen_kappa_score([h for h,m in zip(human_consensus, mask) if m],
                           [j for j,m in zip(judge_pref,       mask) if m])
pct    = sum(h == j for h,j,m in zip(human_consensus, judge_pref, mask) if m) / sum(mask)
```
Headline: **κ(judge, human-consensus)** + raw % agreement, per task type and overall.

## Step D — Bias probes (deliberate, not just observational)

```python
# Position bias — humans: does "Response 1" win regardless of content?
p_r1 = mean(choice == "R1" for non-tie labels)          # ~0.5 = unbiased
# controlled on the exemplar items (we know the strong side): win-rate of the
# strong answer when shown as R1 vs as R2 — a gap = position bias.
# Position bias — judge: run each pair in BOTH orders; flip_rate = P(pick changes).

# Length bias — did the longer response win?
from scipy.stats import pointbiserialr
r, p = pointbiserialr(chose_longer_01, was_preferred_01)   # compare judge vs humans

# Self-preference — if a candidate shares the judge's model family, compare the
# judge's pick-rate for it against the humans' pick-rate for the same pairs.
```

## Step E — Pairwise → rating (Bradley-Terry)

```python
import choix
# pairs = [(winner_system_idx, loser_system_idx), ...]  (drop ties)
ratings = choix.ilsr_pairwise(n_systems, pairs, alpha=0.01)   # higher = stronger
# rank systems by `ratings`; differences map to win-probabilities via the logistic.
```
Pure-numpy MLE fallback (no dependency): maximize
`Σ log σ(θ_winner − θ_loser)` over `θ` by gradient ascent; fix `θ_0 = 0` for
identifiability. **A real ranking now:** with 3 candidate models
(Qwen2.5-7B-Instruct, GPT-4.1-mini, Mistral-7B-Instruct) the ratings form a
genuine leaderboard, not just a win-rate. **Scope:** BT as a *rating* is in-scope
eval; BT/DPO as *training* is Track 3 (local until mentor sign-off).

## Step F — From survey to DPO data

The survey doubles as a preference-collection run. Every comparison includes
**Qwen2.5-7B-Instruct**, so each human preference is an on-policy pair for the DPO
target. Three inputs join into `(prompt, chosen, rejected)`:

- survey labels — `(rater_id, version, item_id, choice ∈ {R1,R2,tie})`
- `version_map.csv` — `item_id → (response1_model, response2_model)`
- **responses store** `responses.jsonl` — `{source, model, text}` (a model's answer
  to a prompt, keyed by prompt `source`; without the *text*, the votes can't train)
- **item pool** `item_pool.jsonl` — `item_id → (source, prompt)`

```python
# 0) item_id -> prompt source & text (from item_pool.jsonl). responses.jsonl keys on
#    SOURCE, not item_id, since a model's answer to a prompt is shared across the
#    items that reuse that prompt.
src            = {it["item_id"]: it["source"] for it in item_pool}
prompt_by_item = {it["item_id"]: it["prompt"] for it in item_pool}

# 1) undo display order -> preferred MODEL, then 3-5-vote majority consensus
def preferred_model(choice, r1_model, r2_model):
    return None if choice == "tie" else (r1_model if choice == "R1" else r2_model)
# consensus per item; drop ties / no-majority  ->  item_id: (chosen_model, rejected_model)

# 2) look up the actual response text (keyed by SOURCE, model) and emit the triple
text = {(r["source"], r["model"]): r["text"] for r in responses}   # responses.jsonl
triples = [{
    "prompt":   prompt_by_item[iid],
    "chosen":   text[(src[iid], chosen_model)],
    "rejected": text[(src[iid], rejected_model)],
} for iid, (chosen_model, rejected_model) in consensus_by_item.items()]

from datasets import Dataset
dpo_ds = Dataset.from_list(triples)      # prompt/chosen/rejected == trl.DPOTrainer input
```

**Scaling path** — ~100 human pairs is a *seed*, not a full 7B DPO set. The human
set's real job is to **calibrate the judge (the κ)**; the calibrated judge then
labels many more pairs cheaply:

```
human pairs (~100, gold) ──calibrate──▶ judge (Cohen's κ)
        │                                    │
        │                   calibrated judge labels more model-vs-model
        │                   pairs (keep only high-margin)      +
        └──────────────▶  execution-verified pairs (SQL: pass=chosen, fail=rejected)
                                             =
                        low-thousands of DPO pairs ──▶ QLoRA-DPO
                        Qwen2.5-1.5B (fast off-policy fallback) → 7B (on-policy)
```

Guards: keep only judge labels above a confidence margin (don't train on the
judge's mistakes); dedupe by prompt; hold out a test split for the win-rate metric.
**Scope:** the DPO run itself is Track 3 — local, not pushed until mentor sign-off.

## Synthetic self-tests (run offline before real data)

```python
# Cohen's kappa: perfect agreement -> 1.0; independent -> ~0.0
assert cohen_kappa_score(["X","Y","X","Y"], ["X","Y","X","Y"]) == 1.0
# consensus: 2/3 majority resolves; 3-way split -> no_consensus
assert consensus(["X","X","Y"]) == "X"
assert consensus(["X","Y","tie"]) == "no_consensus"
# to_system_pref undoes order: R1 with strong shown 2nd recovers the right system
assert to_system_pref("R2", "X") == "Y"
# Bradley-Terry: a system that always wins ranks highest
```

## Output: `docs/validation-study.md`

| metric | value | reading |
|---|---|---|
| Human agreement (Krippendorff α / Fleiss κ) | _tbd_ | the ceiling; gate ≥ 0.40 |
| Judge vs human (Cohen's κ) | _tbd_ | headline; compare to the ceiling |
| Judge vs human (% agreement) | _tbd_ | intuitive companion to κ |
| Position bias (P(R1), judge flip-rate) | _tbd_ | ~0.5 / low = unbiased |
| Length bias (point-biserial r) | _tbd_ | ~0 = no length preference |
| Bradley-Terry ratings | _tbd_ | model ranking from preferences |

The line that sells it: **"the judge agrees with humans (κ = X) about as well as
humans agree with each other (α = Y)."**
