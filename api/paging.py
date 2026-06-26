"""Shared list pagination for api/ blueprints."""

from __future__ import annotations

from flask import request

from api.responses import err

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def parse_paging() -> tuple[tuple[int, int] | None, tuple | None]:
    """Parse ?limit / ?offset. Returns ((limit, offset), None) or (None, err)."""
    raw_limit = request.args.get("limit", DEFAULT_LIMIT)
    raw_offset = request.args.get("offset", 0)
    try:
        limit, offset = int(raw_limit), int(raw_offset)
    except (TypeError, ValueError):
        return None, err("limit and offset must be integers", 400)
    if limit < 0 or offset < 0:
        return None, err("limit and offset must be non-negative", 400)
    return (min(limit, MAX_LIMIT), offset), None


def page_rows(rows: list, limit: int, offset: int) -> dict:
    """Build meta dict for a paged list response."""
    total = len(rows)
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
    }
