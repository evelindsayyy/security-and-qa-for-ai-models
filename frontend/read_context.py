"""Read-path context for visibility filtering."""

from __future__ import annotations


def read_context() -> tuple[str, str | None]:
    """Return (view_mode, user_id) for data layer queries."""
    try:
        from auth.session import effective_user, get_view_mode

        user = effective_user()
        uid = user.get("id") if user else None
        return get_view_mode(), uid
    except Exception:
        return "public", None
