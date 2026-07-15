"""Launch context helpers — view mode, current user, visibility."""

from __future__ import annotations

from typing import Any

from flask import has_request_context, session


def auth_enabled() -> bool:
    import os

    from dbutils.env import load_repo_env

    load_repo_env()
    return os.environ.get("AUTH_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def get_view_mode() -> str:
    if has_request_context():
        mode = session.get("view_mode", "public")
        return mode if mode in ("public", "private") else "public"
    return "public"


def set_view_mode(mode: str) -> None:
    if mode not in ("public", "private"):
        mode = "public"
    session["view_mode"] = mode


def current_user() -> dict[str, Any] | None:
    if not has_request_context():
        return None
    user = session.get("user")
    return user if isinstance(user, dict) else None


def current_user_id() -> str | None:
    user = current_user()
    return user.get("id") if user else None


def is_logged_in() -> bool:
    return current_user() is not None


def is_allowlisted(user: dict[str, Any] | None = None) -> bool:
    import os

    from dbutils.env import load_repo_env

    load_repo_env()
    u = user or effective_user()
    if not u:
        if not auth_enabled():
            dev = os.environ.get("AUTH_DEV_NETID", "").strip().lower()
            return bool(dev)
        return False
    if not auth_enabled():
        return True
    allowed_raw = os.environ.get("AUTH_ALLOWED_NETIDS", "")
    allowed = {n.strip().lower() for n in allowed_raw.split(",") if n.strip()}
    if not allowed:
        return False
    return str(u.get("netid", "")).lower() in allowed


def login_user(user: dict[str, Any]) -> None:
    session.pop("dev_logged_out", None)
    session["user"] = user
    session.permanent = True


def logout_user() -> None:
    session.pop("user", None)
    session["dev_logged_out"] = True
    set_view_mode("public")
    from frontend.read_context import invalidate_view_caches

    invalidate_view_caches()


def dev_user_from_env() -> dict[str, Any] | None:
    """When AUTH_ENABLED=0, build a dev user from AUTH_DEV_NETID (login route only)."""
    import os
    import uuid

    from dbutils.env import load_repo_env

    load_repo_env()
    if auth_enabled():
        return None
    if session.get("dev_logged_out"):
        return None
    netid = os.environ.get("AUTH_DEV_NETID", "").strip().lower()
    if not netid:
        return None
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"dev-user:{netid}")),
        "netid": netid,
        "email": f"{netid}@duke.edu",
        "display_name": netid,
    }


def dev_login_available() -> bool:
    return not auth_enabled() and dev_user_from_env() is not None


def effective_user() -> dict[str, Any] | None:
    return current_user()


def sync_session_for_auth() -> None:
    """Logged-out users always see the public catalog."""
    if not has_request_context():
        return
    if not is_logged_in() and get_view_mode() != "public":
        set_view_mode("public")
        from frontend.read_context import invalidate_view_caches

        invalidate_view_caches()


def require_private_access() -> tuple[dict[str, Any] | None, str | None]:
    """Return (user, error_message) for private-mode actions."""
    if get_view_mode() != "private":
        return None, "Switch to private view to use this feature."
    user = effective_user()
    if not user:
        return None, "Sign in with your Duke NetID to continue."
    if not is_allowlisted(user):
        return None, "Your NetID is not authorized for private mode."
    return user, None


def auth_context_for_template() -> dict[str, Any]:
    user = current_user()
    return {
        "auth_enabled": auth_enabled(),
        "dev_login_available": dev_login_available(),
        "view_mode": get_view_mode(),
        "current_user": user,
        "is_logged_in": user is not None,
        "is_allowlisted": is_allowlisted(user) if user else False,
    }
