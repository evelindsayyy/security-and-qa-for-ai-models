"""Auth routes — Duke OIDC login, callback, logout, view mode."""

from __future__ import annotations

import secrets

from flask import Blueprint, jsonify, redirect, render_template_string, request, session, url_for

from auth.oidc import init_oauth, oauth, redirect_uri
from auth.session import (
    auth_enabled,
    auth_context_for_template,
    effective_user,
    is_allowlisted,
    login_user,
    logout_user,
    set_view_mode,
)
from dbutils.run_access import upsert_user

bp = Blueprint("auth", __name__, url_prefix="/auth")

_POPUP_DONE_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Signed in</title></head>
<body>
<script>
  if (window.opener) {
    window.opener.postMessage({type: "auth-complete"}, window.location.origin);
    window.close();
  } else {
    window.location.href = {{ home_url|tojson }};
  }
</script>
<p>Signed in. You can close this tab.</p>
</body></html>
"""


def register_auth(app) -> None:
    init_oauth(app)
    app.register_blueprint(bp)
    app.context_processor(lambda: auth_context_for_template())


@bp.route("/login")
def login():
    if not auth_enabled():
        dev = effective_user()
        if dev:
            login_user(dev)
            return _finish_login(popup=request.args.get("popup") == "1")
        return "AUTH_ENABLED=0 — set AUTH_DEV_NETID for local login.", 400

    if effective_user() and is_allowlisted(effective_user()):
        return _finish_login(popup=request.args.get("popup") == "1")

    client = oauth.create_client("duke")
    if client is None:
        return "OIDC not configured — set DUKE_OIDC_CLIENT_ID in .env", 503

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["oauth_popup"] = request.args.get("popup") == "1"
    session["oauth_next"] = request.args.get("next") or url_for("index")
    return client.authorize_redirect(redirect_uri(), state=state)


@bp.route("/callback")
def callback():
    if not auth_enabled():
        return redirect(url_for("index"))

    client = oauth.create_client("duke")
    if client is None:
        return "OIDC not configured", 503

    expected_state = session.pop("oauth_state", None)
    if not expected_state or request.args.get("state") != expected_state:
        return "Invalid OAuth state.", 400

    try:
        token = client.authorize_access_token()
    except Exception as exc:
        return f"OAuth token exchange failed: {exc}", 400

    userinfo = token.get("userinfo")
    if not userinfo:
        try:
            userinfo = client.userinfo()
        except Exception:
            userinfo = {}

    netid = (
        userinfo.get("dukeNetID")
        or userinfo.get("preferred_username")
        or (userinfo.get("sub") or "").split("@")[0]
    )
    netid = str(netid).strip().lower()
    if not netid:
        return "Could not read dukeNetID from OIDC response.", 400

    email = userinfo.get("email")
    display_name = userinfo.get("name") or userinfo.get("given_name")

    user_id = _persist_user(netid=netid, email=email, display_name=display_name)
    user = {
        "id": user_id,
        "netid": netid,
        "email": email,
        "display_name": display_name or netid,
    }
    login_user(user)

    if not is_allowlisted(user):
        logout_user()
        return "Your NetID is not authorized for this application.", 403

    popup = session.pop("oauth_popup", False)
    return _finish_login(popup=popup)


def _persist_user(*, netid: str, email: str | None, display_name: str | None) -> str:
    from dbutils.connection import psycopg_available
    from dbutils.env import load_repo_env, resolve_dsn

    load_repo_env()
    dsn = resolve_dsn("POSTGRES_DSN", "DATABASE_URL", "EFFICACY_DB_DSN")
    if dsn and psycopg_available():
        try:
            import psycopg

            with psycopg.connect(dsn, connect_timeout=3) as conn:
                return upsert_user(
                    conn,
                    netid=netid,
                    email=email,
                    display_name=display_name,
                )
        except Exception:
            pass
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user:{netid}"))


def _finish_login(*, popup: bool):
    next_url = session.pop("oauth_next", None) or url_for("index")
    if popup:
        return render_template_string(
            _POPUP_DONE_HTML,
            home_url=next_url,
        )
    return redirect(next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True})
    return redirect(request.referrer or url_for("index"))


@bp.route("/me")
def me():
    user = effective_user()
    return jsonify(
        {
            "ok": True,
            "authenticated": user is not None,
            "allowlisted": is_allowlisted(user) if user else False,
            "user": user,
            **auth_context_for_template(),
        }
    )


@bp.route("/view-mode", methods=["POST"])
def view_mode():
    mode = request.form.get("mode")
    if not mode and request.is_json:
        payload = request.get_json(silent=True) or {}
        mode = payload.get("mode")
    if mode not in ("public", "private"):
        return jsonify({"ok": False, "error": "mode must be public or private"}), 400
    if mode == "private":
        user = effective_user()
        if not user or not is_allowlisted(user):
            return jsonify({"ok": False, "error": "login required for private view"}), 403
    set_view_mode(mode)
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True, "view_mode": mode})
    return redirect(request.referrer or url_for("index"))
