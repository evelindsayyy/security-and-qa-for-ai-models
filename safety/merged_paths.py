"""Discover merged_safety_result.json files (profile-scoped and legacy layouts)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def merged_result_path(output_dir: Path, slug: str, profile: str = "base") -> Path:
    """Path to merged_safety_result.json for one (slug, profile) pair."""
    scoped = output_dir / slug / profile / "merged_safety_result.json"
    if scoped.is_file():
        return scoped
    if profile == "base":
        legacy = output_dir / slug / "merged_safety_result.json"
        if legacy.is_file():
            return legacy
    return scoped


def iter_merged_result_paths(output_dir: Path) -> Iterator[tuple[Path, str, str]]:
    """Yield ``(path, slug, profile)`` for every merged result under *output_dir*.

    Profile-scoped layout: ``<slug>/<profile>/merged_safety_result.json``
    Legacy layout (treated as profile ``base``): ``<slug>/merged_safety_result.json``
    """
    if not output_dir.is_dir():
        return

    seen: set[tuple[str, str]] = set()
    for path in sorted(output_dir.glob("*/*/merged_safety_result.json")):
        profile = path.parent.name
        slug = path.parent.parent.name
        key = (slug, profile)
        if key in seen:
            continue
        seen.add(key)
        yield path, slug, profile

    for path in sorted(output_dir.glob("*/merged_safety_result.json")):
        slug = path.parent.name
        key = (slug, "base")
        if key in seen:
            continue
        seen.add(key)
        yield path, slug, "base"
