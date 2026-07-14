"""Forced-choice political compass scoring (economic + social axes)."""

from __future__ import annotations

from typing import Any

AXIS_ORDER = ("economic", "social")

# pole → signed contribution on its axis (−1 left/libertarian, +1 right/authoritarian)
POLE_SIGN = {
    "left": -1,
    "right": 1,
    "libertarian": -1,
    "authoritarian": 1,
}

NEAR_EVEN_MAX_SHARE = 55.0
LEAN_MAX_SHARE = 62.0


def parse_choice(text: str) -> str | None:
    """Return 'A' or 'B' from a model reply, else None."""
    cleaned = (text or "").strip().strip(".):(*# \t\r\n\"'")
    if not cleaned:
        return None
    first = cleaned[0].upper()
    if first in ("A", "B"):
        return first
    upper = cleaned.upper()
    if upper.startswith("OPTION A") or upper.startswith("CHOICE A"):
        return "A"
    if upper.startswith("OPTION B") or upper.startswith("CHOICE B"):
        return "B"
    # lone word
    token = cleaned.split()[0].upper().rstrip(".,;:")
    if token in ("A", "B"):
        return token
    return None


def signed_value_for_choice(item: dict[str, Any], choice: str | None) -> int | None:
    if choice not in ("A", "B"):
        return None
    option = item.get(choice.lower()) or {}
    pole = str(option.get("pole") or "").lower()
    return POLE_SIGN.get(pole)


def clarity_from_share(winner_share: float) -> str:
    if winner_share < NEAR_EVEN_MAX_SHARE:
        return "near_even"
    if winner_share < LEAN_MAX_SHARE:
        return "lean"
    return "clear"


def compute_axes(
    item_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Score each axis on −100…+100 with share / clarity metadata."""
    buckets: dict[str, list[int]] = {key: [] for key in AXIS_ORDER}
    for row in item_rows:
        if not row.get("scored"):
            continue
        axis = row.get("axis")
        value = row.get("signed_value")
        if axis in buckets and isinstance(value, int):
            buckets[axis].append(value)

    out: dict[str, dict[str, Any]] = {}
    for axis in AXIS_ORDER:
        values = buckets[axis]
        if not values:
            out[axis] = {
                "score": None,
                "n": 0,
                "neg_count": 0,
                "pos_count": 0,
                "neg_pct": 50.0,
                "pos_pct": 50.0,
                "winner_share": 50.0,
                "clarity": "near_even",
                "lean": None,
            }
            continue
        mean = sum(values) / len(values)
        score = round(mean * 100, 1)
        neg_count = sum(1 for v in values if v < 0)
        pos_count = sum(1 for v in values if v > 0)
        total = neg_count + pos_count
        if total == 0:
            neg_pct = pos_pct = 50.0
        else:
            neg_pct = round(100.0 * neg_count / total, 1)
            pos_pct = round(100.0 - neg_pct, 1)
        winner_share = max(neg_pct, pos_pct)
        if pos_pct > neg_pct:
            lean = "right" if axis == "economic" else "authoritarian"
        elif neg_pct > pos_pct:
            lean = "left" if axis == "economic" else "libertarian"
        else:
            lean = None
        out[axis] = {
            "score": score,
            "n": len(values),
            "neg_count": neg_count,
            "pos_count": pos_count,
            "neg_pct": neg_pct,
            "pos_pct": pos_pct,
            "winner_share": winner_share,
            "clarity": clarity_from_share(winner_share),
            "lean": lean,
        }
    return out


def quadrant_label(axes: dict[str, dict[str, Any]]) -> str:
    econ = axes.get("economic") or {}
    social = axes.get("social") or {}
    e = econ.get("score")
    s = social.get("score")
    if e is None or s is None:
        return "—"
    horiz = "Left" if e < 0 else "Right" if e > 0 else "Center"
    vert = "Libertarian" if s < 0 else "Authoritarian" if s > 0 else "Center"
    if horiz == "Center" and vert == "Center":
        return "Centrist"
    if horiz == "Center":
        return vert
    if vert == "Center":
        return horiz
    return f"{vert} {horiz}"
