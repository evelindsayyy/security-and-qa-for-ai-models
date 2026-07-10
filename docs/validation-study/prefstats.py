"""
prefstats.py — the preference-study statistics, in pure numpy.

The analysis_plan.md spec reaches for scikit-learn / statsmodels / choix, none of
which are installed (and adding them risks the pillar's datasets dep conflict).
Every metric here is a short, self-contained numpy implementation with the same
result, so analyze.py needs only numpy — and each has a synthetic self-test in
unit_tests/test_prefstats.py that pins it against a known value.

The functions are pure (no I/O): choices in, numbers out.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional, Sequence

import numpy as np

TIE = "tie"
NO_CONSENSUS = "no_consensus"


# ---------------------------------------------------------------------------
# Undo display order + consensus
# ---------------------------------------------------------------------------


def to_system_pref(choice: str, r1_system: str, r2_system: str) -> str:
    """Turn a positional pick into a claim about the SYSTEM, not the position.

    choice ∈ {"R1","R2","tie"}; r1/r2_system are the models shown as Response 1/2.
    Returns the preferred system id, or "tie".
    """
    if choice == TIE:
        return TIE
    if choice == "R1":
        return r1_system
    if choice == "R2":
        return r2_system
    raise ValueError(f"bad choice {choice!r} (expected R1/R2/tie)")


def consensus(prefs: Sequence[str]) -> str:
    """Majority label among an item's raters, or NO_CONSENSUS if none reaches a
    strict majority (> half). Ties between systems and 'tie' votes count as votes;
    a 3-way split (or a 1-1-1) yields no consensus."""
    if not prefs:
        return NO_CONSENSUS
    top, count = Counter(prefs).most_common(1)[0]
    return top if count > len(prefs) / 2 else NO_CONSENSUS


def preferred_model(choice: str, r1_model: str, r2_model: str) -> Optional[str]:
    """The chosen MODEL for a non-tie pick (for Bradley-Terry / DPO), else None."""
    if choice == TIE:
        return None
    return r1_model if choice == "R1" else r2_model


# ---------------------------------------------------------------------------
# Agreement
# ---------------------------------------------------------------------------


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's κ between two raters' aligned labels. 1.0 = perfect, ~0 = chance."""
    a, b = list(a), list(b)
    if len(a) != len(b):
        raise ValueError("cohen_kappa: unequal lengths")
    n = len(a)
    if n == 0:
        return 0.0
    cats = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    if pe >= 1.0:                      # both raters used one category → κ undefined
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def fleiss_kappa(table: np.ndarray | Sequence[Sequence[float]]) -> float:
    """Fleiss' κ for a fixed number of raters per item.

    ``table`` is items × categories, table[i][j] = how many raters put item i in
    category j (each row sums to the (constant) rater count). Our design has
    exactly 3 raters/item, so this applies cleanly.
    """
    counts = np.asarray(table, dtype=float)
    N, _ = counts.shape
    per_item = counts.sum(axis=1)
    n_r = per_item[0]
    if not np.allclose(per_item, n_r):
        raise ValueError("fleiss_kappa: unequal raters per item (use Krippendorff)")
    if n_r < 2:
        return 0.0
    # P_i: pairwise agreement within each item
    P_i = (np.square(counts).sum(axis=1) - n_r) / (n_r * (n_r - 1))
    P_bar = P_i.mean()
    p_j = counts.sum(axis=0) / (N * n_r)         # overall category proportions
    P_e = float(np.square(p_j).sum())
    if P_e >= 1.0:
        return 1.0 if P_bar >= 1.0 else 0.0
    return float((P_bar - P_e) / (1.0 - P_e))


def labels_to_fleiss_table(
    item_labels: Sequence[Sequence[str]], categories: Optional[Sequence[str]] = None
) -> np.ndarray:
    """Rows of per-item labels → the items × categories count table fleiss_kappa
    wants. ``categories`` fixes the column order (default: sorted union)."""
    if categories is None:
        categories = sorted({lab for row in item_labels for lab in row})
    idx = {c: j for j, c in enumerate(categories)}
    table = np.zeros((len(item_labels), len(categories)), dtype=float)
    for i, row in enumerate(item_labels):
        for lab in row:
            table[i, idx[lab]] += 1
    return table


# ---------------------------------------------------------------------------
# Bias
# ---------------------------------------------------------------------------


def point_biserial(binary: Sequence[float], continuous: Sequence[float]) -> float:
    """Point-biserial r = Pearson correlation of a 0/1 variable with a continuous
    one. Used for length bias: r(chose_longer, was_preferred). ~0 = no preference."""
    x = np.asarray(binary, dtype=float)
    y = np.asarray(continuous, dtype=float)
    if x.size < 2 or x.std() == 0 or y.std() == 0:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


# ---------------------------------------------------------------------------
# Pairwise → rating (Bradley-Terry, numpy MLE)
# ---------------------------------------------------------------------------


def bradley_terry(
    n_systems: int,
    pairs: Iterable[tuple[int, int]],
    *,
    iters: int = 3000,
    lr: float = 0.1,
    l2: float = 1e-3,
) -> np.ndarray:
    """Bradley-Terry strengths θ from (winner_idx, loser_idx) pairs, by gradient
    ascent on Σ log σ(θ_winner − θ_loser). θ_0 is pinned to 0 for identifiability;
    higher θ = stronger. Ties should be dropped before calling."""
    pairs = list(pairs)
    theta = np.zeros(n_systems)
    if not pairs:
        return theta
    for _ in range(iters):
        grad = np.zeros(n_systems)
        for w, ell in pairs:
            p_w = 1.0 / (1.0 + np.exp(-(theta[w] - theta[ell])))   # P(w beats ell)
            grad[w] += 1.0 - p_w
            grad[ell] -= 1.0 - p_w
        grad -= l2 * theta                    # keep strengths bounded
        theta += lr * grad
        theta -= theta[0]                     # pin θ_0 = 0
    return theta


def bradley_terry_ranking(
    systems: Sequence[str], pairs_by_name: Iterable[tuple[str, str]], **kw
) -> list[tuple[str, float]]:
    """Convenience wrapper: (winner_name, loser_name) pairs → [(system, θ)] sorted
    strongest first."""
    systems = list(systems)
    idx = {s: i for i, s in enumerate(systems)}
    pairs = [(idx[w], idx[ell]) for w, ell in pairs_by_name if w in idx and ell in idx]
    theta = bradley_terry(len(systems), pairs, **kw)
    ranked = sorted(zip(systems, theta), key=lambda t: t[1], reverse=True)
    return [(s, float(v)) for s, v in ranked]


def kappa_reading(k: float) -> str:
    """Landis–Koch interpretation of a κ/α value."""
    if k < 0:
        return "poor"
    if k <= 0.20:
        return "slight"
    if k <= 0.40:
        return "fair"
    if k <= 0.60:
        return "moderate"
    if k <= 0.80:
        return "substantial"
    return "almost perfect"
