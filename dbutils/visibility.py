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
    params: dict[str, Any] = {}
    if view_mode != "private" or not user_id:
        return f"{table_alias}.visibility = 'public'", params

    params["uid"] = user_id
    link_exists = ""
    if links_alias:
        link_exists = f"""
            OR EXISTS (
                SELECT 1 FROM public.user_run_links url
                WHERE url.user_id = %(uid)s
                  AND url.run_id = {table_alias}.id
            )
        """
    return (
        f"""(
            {table_alias}.visibility = 'public'
            OR ({table_alias}.visibility = 'private' AND {table_alias}.owner_user_id = %(uid)s)
            {link_exists}
        )""",
        params,
    )


def artifact_visible(
    meta: dict[str, Any],
    *,
    view_mode: str,
    user_id: str | None,
) -> bool:
    """Filter on-disk artifacts by run_meta visibility."""
    visibility = meta.get("visibility", "public")
    if visibility == "public":
        return True
    if view_mode != "private" or not user_id:
        return False
    owner = meta.get("owner_user_id")
    return owner == user_id
