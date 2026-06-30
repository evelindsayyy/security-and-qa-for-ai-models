"""Auth route guards."""

from __future__ import annotations

from functools import wraps

from flask import jsonify, redirect, request, url_for

from auth.session import effective_user, is_allowlisted, require_private_access


def require_login(*, api: bool = False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = effective_user()
            if not user:
                if api:
                    return jsonify({"ok": False, "error": "authentication required"}), 401
                return redirect(url_for("auth.login", next=request.path, popup=1))
            if not is_allowlisted(user):
                if api:
                    return jsonify({"ok": False, "error": "not authorized"}), 403
                return "Your NetID is not authorized.", 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_private_login(*, api: bool = False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user, err = require_private_access()
            if err:
                if api:
                    return jsonify({"ok": False, "error": err}), 403
                return err, 403
            request.auth_user = user  # type: ignore[attr-defined]
            return fn(*args, **kwargs)

        return wrapper

    return decorator
