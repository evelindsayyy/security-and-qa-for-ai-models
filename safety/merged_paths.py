"""Discover merged_safety_result.json files (profile-scoped and legacy layouts)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from dbutils.run_paths import PRIVATE_SEGMENT
from dbutils import fs_safe


def merged_result_path(
    output_dir: Path, slug: str, profile: str = "base", *, owner_user_id: str | None = None
) -> Path:
    """Path to merged_safety_result.json for one (slug, profile) pair.

    ``owner_user_id`` selects that owner's private copy
    (``<slug>/.private/<uid>/<profile>/…``) instead of the public one.
    """
    if owner_user_id is not None:
        return (
            output_dir / slug / PRIVATE_SEGMENT / owner_user_id / profile
            / "merged_safety_result.json"
        )
    scoped = output_dir / slug / profile / "merged_safety_result.json"
    if fs_safe.is_file(scoped):
        return scoped
    if profile == "base":
        legacy = output_dir / slug / "merged_safety_result.json"
        if fs_safe.is_file(legacy):
            return legacy
    return scoped


def iter_merged_result_paths(
    output_dir: Path, *, owner_user_id: str | None = None
) -> Iterator[tuple[Path, str, str]]:
    """Yield ``(path, slug, profile)`` for every merged result under *output_dir*.

    ``owner_user_id=None`` (default): **public** results only —
    profile-scoped ``<slug>/<profile>/merged_safety_result.json`` and legacy
    ``<slug>/merged_safety_result.json``. Byte-identical to before private
    runs existed — a private result's path is at least two segments deeper
    than either public glob matches, so it can never be picked up here.

    ``owner_user_id=<uid>``: private results for that owner only —
    ``<slug>/.private/<uid>/<profile>/merged_safety_result.json`` (see
    dbutils.run_paths for why private lives nested one level inside the
    slug dir here, unlike scanner's sibling-of-everything layout).
    """
    if not fs_safe.is_dir(output_dir):
        return

    if owner_user_id is not None:
        seen: set[tuple[str, str]] = set()
        pattern = f"*/{PRIVATE_SEGMENT}/{owner_user_id}/*/merged_safety_result.json"
        for path in sorted(fs_safe.glob(output_dir, pattern)):
            profile = path.parent.name
            slug = path.parent.parent.parent.parent.name
            key = (slug, profile)
            if key in seen:
                continue
            seen.add(key)
            yield path, slug, profile
        return

    seen = set()
    for path in sorted(fs_safe.glob(output_dir, "*/*/merged_safety_result.json")):
        profile = path.parent.name
        slug = path.parent.parent.name
        key = (slug, profile)
        if key in seen:
            continue
        seen.add(key)
        yield path, slug, profile

    for path in sorted(fs_safe.glob(output_dir, "*/merged_safety_result.json")):
        slug = path.parent.name
        key = (slug, "base")
        if key in seen:
            continue
        seen.add(key)
        yield path, slug, "base"
