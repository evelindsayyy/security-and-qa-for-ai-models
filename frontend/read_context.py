"""Read-path context for visibility filtering."""

from __future__ import annotations


def read_context() -> tuple[str, str | None]:
    """Return (view_mode, user_id) for data layer queries."""
    try:
        from auth.session import current_user, get_view_mode

        user = current_user()
        uid = user.get("id") if user else None
        return get_view_mode(), uid
    except Exception:
        return "public", None


def artifact_path_visible(directory, *, pillar: str = "generic") -> bool:
    """Whether an on-disk run directory should appear in the current view."""
    from dbutils.run_meta import read_run_meta_for_pillar
    from dbutils.visibility import artifact_visible

    view_mode, user_id = read_context()
    meta = read_run_meta_for_pillar(directory, pillar=pillar)
    return artifact_visible(meta, view_mode=view_mode, user_id=user_id)


def invalidate_view_caches() -> None:
    """Drop request-scoped and in-process caches keyed on public/private view."""
    try:
        from flask import g, has_request_context

        if has_request_context():
            g.pop("_overview_pillar_payloads", None)
    except Exception:
        pass
    try:
        from frontend.model_rollup import clear_models_union_cache

        clear_models_union_cache()
    except Exception:
        pass
