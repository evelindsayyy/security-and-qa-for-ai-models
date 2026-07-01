"""SQL visibility filters for pillar read paths."""

from __future__ import annotations

from typing import Any


def visibility_clause(
    table_alias: str,
    *,
    view_mode: str,
    user_id: str | None,
    links_alias: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (SQL fragment, params) for filtering runs by view mode."""
    del links_alias  # user_run_links are for dedup only, not private catalog reads
    params: dict[str, Any] = {}
    if view_mode != "private" or not user_id:
        return f"{table_alias}.visibility = 'public'", params

    params["uid"] = user_id
    return (
        f"({table_alias}.visibility = 'private' AND {table_alias}.owner_user_id = %(uid)s)",
        params,
    )


def artifact_visible(
    meta: dict[str, Any],
    *,
    view_mode: str,
    user_id: str | None,
) -> bool:
    """Filter on-disk artifacts by run_meta visibility."""
    visibility = (meta or {}).get("visibility", "public")
    if view_mode != "private" or not user_id:
        return visibility == "public"
    if visibility != "private":
        return False
    owner = meta.get("owner_user_id")
    return owner == user_id
