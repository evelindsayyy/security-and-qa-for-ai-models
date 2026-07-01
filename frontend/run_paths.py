"""Pillar-agnostic on-disk path scoping by visibility + owner.

Public artifacts keep the flat layout every pillar has always used — zero
migration, existing URLs and directories untouched. Private artifacts live
in a **sibling** tree, never nested inside a slug's own directory.

That sibling placement matters: starting a fresh run of a model wipes its
staging directory outright (``shutil.rmtree`` on the whole slug dir) before
writing new output. If a private artifact lived *inside* that same slug
directory (e.g. ``output/<slug>/.private/<owner>/``), a public rerun of that
model would silently delete every user's private data for it. Keeping
".private" as a sibling of whatever directory actually gets wiped on rerun —
``output/.private/<owner_user_id>/<slug>/`` — means the two trees never
overlap, so a wipe of one can never touch the other.

Pure (no Flask/session imports) so it's trivially unit-testable and safe to
import from the DB loaders (scanner/db/, safety/db/) without circularity.
"""

from __future__ import annotations

from pathlib import Path

PRIVATE_SEGMENT = ".private"
# Leading "." keeps this from ever colliding with a real slug: HF repo ids
# and gateway model ids are both validated to start with an alphanumeric
# character (see frontend.scan_launch._HF_REPO_RE), so no legitimate slug
# can ever be named ".private".


def scoped_dir(base_for_slug: Path, *, visibility: str, owner_user_id: str | None) -> Path:
    """Directory for one run, given the slug's public base directory.

    public  -> base_for_slug                                          (unchanged)
    private -> base_for_slug.parent / ".private" / owner_user_id / base_for_slug.name
    """
    if visibility != "private":
        return base_for_slug
    if not owner_user_id:
        raise ValueError("private visibility requires an owner_user_id")
    return base_for_slug.parent / PRIVATE_SEGMENT / owner_user_id / base_for_slug.name


def inflight_scope_key(visibility: str, owner_user_id: str | None) -> tuple[str, str | None]:
    """Normalized (visibility, owner_user_id) tuple to fold into an in-flight combo key."""
    return (visibility, owner_user_id if visibility == "private" else None)
