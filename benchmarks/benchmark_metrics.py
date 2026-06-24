"""Shared scoring / coverage helpers for benchmark runners."""

from __future__ import annotations

import re


def has_usable_text(text: str | None) -> bool:
    """True when *text* is a non-empty model response worth scoring."""
    return bool(str(text or "").strip())


def slugify_model(name: str) -> str:
    """Filesystem-safe slug for a model id.

    Replaces every char outside ``[A-Za-z0-9._-]`` (e.g. ``/`` and the ``:`` in
    an ``org/model:provider`` pin, which is illegal in Windows filenames) with
    ``_`` so result filenames stay valid on every platform.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "").strip()) or "model"


def compute_coverage(*, attempted: int, scored: int) -> dict[str, int | float]:
    """Return attempted/scored/failed/coverage for a partial run."""
    failed = max(0, attempted - scored)
    return {
        "attempted": attempted,
        "scored": scored,
        "failed": failed,
        "coverage": round(scored / attempted, 4) if attempted > 0 else 0.0,
    }


def summarize_binary_accuracy(
    *,
    attempted: int,
    correct: int,
    scored: int | None = None,
) -> dict[str, int | float]:
    """Accuracy over *scored* items; coverage over *attempted*."""
    if scored is None:
        scored = attempted
    cov = compute_coverage(attempted=attempted, scored=scored)
    accuracy = round(correct / scored, 4) if scored > 0 else 0.0
    return {
        **cov,
        "correct": correct,
        "accuracy": accuracy,
        # Legacy aliases used by different runners / the TQA UI.
        "total_evaluated": scored,
        "total": scored,
    }


def coverage_warning(summary: dict) -> str | None:
    """One-line warning when a run did not fully answer the sample."""
    failed = summary.get("failed", 0)
    if not failed:
        return None
    attempted = summary.get("attempted", 0)
    scored = summary.get("scored", 0)
    coverage = summary.get("coverage", 0)
    return (
        f"  [WARN] only {scored}/{attempted} items answered "
        f"({coverage:.0%} coverage) — {failed} failed; "
        f"accuracy is over answered items only"
    )


def accuracy_bar(accuracy: float, width: int = 40) -> str:
    bar_len = int(accuracy * width)
    return "[" + "=" * bar_len + "-" * (width - bar_len) + "]"


def coverage_extras(summary: dict) -> dict[str, int | float]:
    """Subset of *summary* worth surfacing when a run was partial."""
    if not summary.get("failed"):
        return {}
    return {
        "attempted": summary["attempted"],
        "scored": summary["scored"],
        "failed": summary["failed"],
        "coverage": summary["coverage"],
    }


def print_binary_summary(
    label: str,
    summary: dict,
    *,
    correct_key: str = "correct",
    scored_key: str = "scored",
    title: str = "SUMMARY",
) -> None:
    """Print a standard accuracy bar + optional coverage warning."""
    correct = summary[correct_key]
    scored = summary.get(scored_key, summary.get("total_evaluated", summary.get("total", 0)))
    accuracy = summary["accuracy"]
    bar = accuracy_bar(accuracy)

    print(f"\n{'=' * 70}")
    print(title)
    print(f"{'=' * 70}")
    print(f"{label:40s} {bar} {accuracy:.1%} ({correct}/{scored})")
    warn = coverage_warning(summary)
    if warn:
        print(warn)
