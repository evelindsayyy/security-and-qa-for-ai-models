"""Shared helpers for POST job endpoints."""

from __future__ import annotations

from typing import Any

from flask import jsonify, request

from api.responses import err
from frontend.output_dirs import OutputDirError


def parse_json_body() -> dict[str, Any]:
    """Return the JSON request body, or an empty dict."""
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def accepted(job_id: str, status_url: str, *, already_running: bool = False):
    """202 Accepted envelope for async pillar jobs."""
    return jsonify(
        {
            "ok": True,
            "data": {
                "job_id": job_id,
                "status": "running",
                "status_url": status_url,
                "already_running": already_running,
            },
            "error": None,
        }
    ), 202


def validation_error(message: str | None):
    """Map validate_launch() return value to a 400 response."""
    return err(message or "invalid request", 400)


def validation_or_launch_error(message: str | None):
    """Return 503 for output-dir failures, 400 for other validation errors."""
    if message and message.startswith("cannot write"):
        return err(message, 503)
    return validation_error(message)


def launch_error_response(exc: OutputDirError):
    """Map output-directory failures to 503 (not a generic 500)."""
    return err(str(exc), 503)


def require_str(body: dict[str, Any], key: str) -> tuple[str | None, tuple | None]:
    """Return (value, None) or (None, err) when a required string field is missing."""
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        return None, err(f"{key} is required", 400)
    return value.strip(), None


def optional_bool(body: dict[str, Any], key: str, *, default: bool = False) -> bool:
    """Parse an optional boolean field from a JSON body."""
    if key not in body:
        return default
    value = body[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
