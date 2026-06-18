"""
Shared JSON envelope for the api/ blueprints.

Every endpoint returns one shape so clients branch on a single contract:
    success: {"ok": true,  "data": <payload>, "error": null}
    list:    {"ok": true,  "data": [...], "error": null, "meta": {"total": N}}
    failure: {"ok": false, "data": null, "error": "<message>"}

(The team's API response convention — see patterns.md / docs/architecture.md.)
"""

from __future__ import annotations

from typing import Any

from flask import jsonify


def ok(data: Any, meta: dict | None = None):
    body: dict[str, Any] = {"ok": True, "data": data, "error": None}
    if meta is not None:
        body["meta"] = meta
    return jsonify(body), 200


def err(message: str, status: int = 400):
    return jsonify({"ok": False, "data": None, "error": message}), status
