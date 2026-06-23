"""
Shared JSON envelope for the api/ blueprints.

Every endpoint returns one shape so clients branch on a single contract:
    success: {"ok": true,  "data": <payload>, "error": null}
    list:    {"ok": true,  "data": [...], "error": null, "meta": {"total": N}}
    failure: {"ok": false, "data": null, "error": "<message>"}

(The team's API response convention — see patterns.md / docs/architecture.md.)
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from flask import current_app, jsonify


def ok(data: Any, meta: dict | None = None):
    body: dict[str, Any] = {"ok": True, "data": data, "error": None}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), 200


def err(message: str, status: int = 400):
    return jsonify({"ok": False, "data": None, "error": message}), status


def json_errors(view: Callable) -> Callable:
    """Wrap a view so an unexpected exception returns the JSON error envelope
    instead of Flask's default HTML 500 page — keeping the "every response is
    the same envelope" contract even when the data layer raises.

    The full traceback is logged server-side (never swallowed); the client
    gets a generic message so internals/paths don't leak.
    """

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except Exception:
            current_app.logger.exception("unhandled API error in %s", view.__name__)
            return err("internal error", 500)

    return wrapper
