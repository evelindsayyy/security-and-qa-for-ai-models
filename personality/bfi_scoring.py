"""BFI-44 scoring helpers (trait averages on a 1–5 Likert scale)."""

from __future__ import annotations

from typing import Any

TRAIT_ORDER = (
    "extraversion",
    "agreeableness",
    "conscientiousness",
    "neuroticism",
    "openness",
)


def reverse_score(raw: int) -> int:
    """Flip a 1–5 Likert response for reverse-keyed items."""
    return 6 - raw


def apply_item_score(raw: int | None, *, reverse: bool) -> int | None:
    if raw is None or raw < 1 or raw > 5:
        return None
    return reverse_score(raw) if reverse else raw


def trait_for_item(item_id: int, traits: dict[str, dict[str, Any]]) -> str | None:
    for key, meta in traits.items():
        if item_id in meta.get("items", []):
            return key
    return None


def compute_trait_scores(
    item_rows: list[dict[str, Any]],
    *,
    traits: dict[str, dict[str, Any]],
) -> dict[str, float | None]:
    """Average scored item values per Big Five trait."""
    buckets: dict[str, list[int]] = {key: [] for key in traits}
    for row in item_rows:
        if not row.get("scored"):
            continue
        value = row.get("scored_value")
        trait = row.get("trait")
        if trait in buckets and isinstance(value, int):
            buckets[trait].append(value)
    out: dict[str, float | None] = {}
    for key in TRAIT_ORDER:
        values = buckets.get(key, [])
        out[key] = round(sum(values) / len(values), 2) if values else None
    return out
