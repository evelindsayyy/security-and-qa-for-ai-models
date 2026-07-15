"""Auth routes — Duke OIDC login, callback, logout, view mode."""

from __future__ import annotations

import logging
import secrets

from flask import Blueprint, current_app, jsonify, redirect, render_template_string, request, session, url_for

from auth.oidc import init_oauth, oauth, redirect_uri
from auth.session import (
    auth_enabled,
    auth_context_for_template,
    current_user,
    dev_user_from_env,
    is_allowlisted,
    login_user,
    logout_user,
    set_view_mode,
    sync_session_for_auth,
)
from dbutils.run_access import upsert_user

bp = Blueprint("auth", __name__, url_prefix="/auth")

_POPUP_DONE_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Signed in</title></head>
<body>
<script>
  if (window.opener) {
    var targetOrigin = {{ opener_origin|tojson }} || window.location.origin;
    window.opener.postMessage({type: "auth-complete"}, targetOrigin);
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
    if auth_enabled():
        app.logger.setLevel(logging.INFO)
    app.register_blueprint(bp)
    app.add_url_rule("/login", view_func=oauth_callback, methods=["GET"])
    app.context_processor(lambda: auth_context_for_template())

    @app.before_request
    def _sync_auth_session():
        sync_session_for_auth()


@bp.route("/login")
def login():
    if not auth_enabled():
        dev = dev_user_from_env()
        if not dev:
            return "AUTH_ENABLED=0 — set AUTH_DEV_NETID for local login.", 400
        if not is_allowlisted(dev):
            return "Your NetID is not authorized for this application.", 403
        login_user(dev)
        return _finish_login(popup=request.args.get("popup") == "1")

    user = current_user()
    if user and is_allowlisted(user):
        return _finish_login(popup=request.args.get("popup") == "1")

    client = oauth.create_client("duke")
    if client is None:
        return "OIDC not configured — set DUKE_OIDC_CLIENT_ID in .env", 503

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    session["oauth_popup"] = request.args.get("popup") == "1"
    session["oauth_next"] = request.args.get("next") or url_for("index")
    session["oauth_opener_origin"] = request.host_url.rstrip("/")
    callback_uri = redirect_uri()
    current_app.logger.info(
        "oauth login start host=%s redirect_uri=%s popup=%s",
        request.host,
        callback_uri,
        session["oauth_popup"],
    )
    try:
        # First network call of the flow: fetches Duke's OIDC discovery
        # document (cached after) and builds the authorize redirect. A
        # timeout or connection error here must not become an unhandled
        # 500 — the public (signed-out) site must keep working regardless
        # of whether this specific login attempt succeeds.
        return client.authorize_redirect(callback_uri, state=state)
    except Exception as exc:
        current_app.logger.warning("oauth authorize redirect failed: %s", exc)
        for key in ("oauth_state", "oauth_popup", "oauth_next", "oauth_opener_origin"):
            session.pop(key, None)
        return f"Could not reach Duke sign-in — try again in a moment: {exc}", 502


@bp.route("/callback")
def callback():
    return oauth_callback()


def oauth_callback():
    """OIDC authorization-code callback (also mounted at GET /login)."""
    if not auth_enabled():
        return redirect(url_for("index"))

    client = oauth.create_client("duke")
    if client is None:
        return "OIDC not configured", 503

    expected_state = session.pop("oauth_state", None)
    received_state = request.args.get("state")
    current_app.logger.info(
        "oauth callback received host=%s code_present=%s state_present=%s expected_state_present=%s",
        request.host,
        bool(request.args.get("code")),
        bool(received_state),
        bool(expected_state),
    )
    if not expected_state or received_state != expected_state:
        current_app.logger.warning(
            "oauth callback invalid state host=%s state_present=%s expected_state_present=%s",
            request.host,
            bool(received_state),
            bool(expected_state),
        )
        return "Invalid OAuth state.", 400

    try:
        token = client.authorize_access_token()
    except Exception as exc:
        current_app.logger.warning("oauth token exchange failed: %s", exc)
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
        current_app.logger.warning("oauth login rejected netid=%s allowlisted=false", netid)
        logout_user()
        return "Your NetID is not authorized for this application.", 403

    current_app.logger.info("oauth login complete netid=%s", netid)
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
            opener_origin=session.pop("oauth_opener_origin", None),
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
    user = current_user()
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
        set_view_mode("private")
        user = current_user()
        if not user or not is_allowlisted(user):
            set_view_mode("public")
            from frontend.read_context import invalidate_view_caches

            invalidate_view_caches()
            if request.headers.get("Accept", "").startswith("application/json"):
                return jsonify({"ok": False, "error": "login required for private view"}), 403
            return redirect(request.referrer or url_for("index"))
    else:
        set_view_mode(mode)
    from frontend.read_context import invalidate_view_caches

    invalidate_view_caches()
    if request.headers.get("Accept", "").startswith("application/json"):
        return jsonify({"ok": True, "view_mode": mode})
    return redirect(request.referrer or url_for("index"))
