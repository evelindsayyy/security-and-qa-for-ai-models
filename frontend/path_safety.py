"""
Guards for URL-supplied slugs that get used in filesystem lookups.

Every detail route (/scans/<slug>, /eval-run/<slug>, /benchmarks/<slug>)
builds a path from a user-controlled slug. These helpers stop traversal
(`../../etc/passwd`-style slugs) before the path is ever touched.
"""

from __future__ import annotations

import re
from pathlib import Path

# Slugs are filename stems produced by our own pipelines: timestamps,
# model ids passed through the runner's _safe_slug, scanner output dirs.
# Letters, digits, dot, dash, underscore only — and never an all-dots
# name like ".." that would traverse upward. `\Z` (not `$`) at both anchor
# points: `$` matches just before a trailing "\n" as well as at the true
# end of the string, so "good\n" would otherwise slip through as "safe".
_SLUG_RE = re.compile(r"(?!\.+\Z)[A-Za-z0-9._-]+\Z")


def is_safe_slug(slug: str) -> bool:
    """True if slug is safe to embed in a filesystem path."""
    return bool(_SLUG_RE.match(slug))


def resolves_inside(base_dir: Path, path: Path) -> bool:
    """True if path resolves to a location inside base_dir (follows symlinks)."""
    try:
        return path.resolve().is_relative_to(base_dir.resolve())
    except OSError:
        return False
