"""
Live Duke AI Gateway model catalog for the draft frontend.

Calls the OpenAI-compatible GET /v1/models endpoint (same base URL + key as
evaluator/_gateway.py). Results are cached briefly so / and /models do not
hammer the gateway on every refresh.

Week 5+: replace with GET /api/models from Postgres.
"""

from __future__ import annotations

import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=False)

_CACHE_TTL_SEC = 300
_cache: dict[str, Any] = {"fetched_at": 0.0, "payload": None}

# Optional team notes keyed by exact LiteLLM id (must match API strings).
ANNOTATIONS: dict[str, str] = {
    "gpt-5-chat": "it_support eval candidate (default)",
    "Llama 4 Maverick": "it_support eval judge (default)",
    "GPT 4.1 Mini": "gateway smoke test (testing/test_gateway.py)",
    "gpt-5-mini": "good pilot tier — low cost",
    "gpt-5-nano": "cheapest openai chat — smoke tier",
    "gpt-5.4": "truthfulqa pilot alias duke-gpt54",
    "Llama 3.3": "truthfulqa pilot alias duke-llama33",
    "gpt-oss-120b": "open-weight style via cloud",
    "Llama 4 Scout": "low-cost llama pilot",
}

# Legacy aliases from week-2 spikes (not returned by /v1/models anymore).
DEPRECATED_IDS: dict[str, str] = {
    "Mistral on-site": "deprecated — phased out; not on gateway allowlist",
}


def _gateway_credentials() -> tuple[str | None, str | None]:
    url = (
        os.environ.get("DUKE_GATEWAY_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("DUKE_GATEWAY_BASE_URL")
    )
    key = (
        os.environ.get("DUKE_GATEWAY_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("DUKE_AI_GATEWAY_API_KEY")
    )
    return url, key


def _categorize(model_id: str) -> str:
    lower = model_id.lower()
    if "codex" in lower:
        return "codex"
    if lower.startswith("whisper") or "transcribe" in lower:
        return "audio"
    if "embedding" in lower:
        return "embeddings"
    if "deep-research" in lower or lower.startswith("o3-") or lower.startswith("o4"):
        return "research"
    if model_id in ("GPT 4.1", "GPT 4.1 Mini", "GPT 4.1 Nano") or lower.startswith(
        "gpt-5"
    ) or lower.startswith("gpt-oss") or model_id.startswith("Llama"):
        return "general_chat"
    return "other"


_CATEGORY_LABELS = {
    "general_chat": "General chat (safety + efficacy)",
    "codex": "Codex / agentic coding",
    "audio": "Audio / transcription",
    "embeddings": "Embeddings",
    "research": "Research / reasoning",
    "other": "Other",
}


def _fetch_live_models() -> tuple[list[dict[str, str]], str | None]:
    """Return (rows, error). Rows sorted by category then id."""
    url, key = _gateway_credentials()
    if not url or not key:
        return [], (
            "Gateway credentials missing — set DUKE_GATEWAY_URL and DUKE_GATEWAY_KEY "
            "(or OPENAI_BASE_URL / OPENAI_API_KEY) in repo-root .env"
        )

    try:
        from openai import OpenAI

        client = OpenAI(base_url=url, api_key=key)
        response = client.models.list()
    except Exception as exc:  # noqa: BLE001 — show message in UI, never crash page
        return [], f"Gateway models.list failed: {type(exc).__name__}: {exc}"

    rows: list[dict[str, str]] = []
    for item in response.data:
        mid = item.id
        rows.append(
            {
                "id": mid,
                "category": _categorize(mid),
                "notes": ANNOTATIONS.get(mid, ""),
                "owned_by": getattr(item, "owned_by", "") or "",
            }
        )

    rows.sort(key=lambda r: (_CATEGORY_LABELS.get(r["category"], r["category"]), r["id"]))
    return rows, None


def get_gateway_catalog(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Cached gateway catalog for templates.

    Returns:
        has_models, models (flat list), by_category (grouped), count, source,
        fetched_at (iso or None), error (str or None), deprecated (legacy ids)
    """
    now = time.time()
    if (
        not force_refresh
        and _cache["payload"] is not None
        and now - _cache["fetched_at"] < _CACHE_TTL_SEC
    ):
        return _cache["payload"]

    models, error = _fetch_live_models()
    by_category: dict[str, list[dict[str, str]]] = {}
    for row in models:
        by_category.setdefault(row["category"], []).append(row)

    payload = {
        "has_models": bool(models),
        "models": models,
        "by_category": [
            {
                "key": key,
                "label": _CATEGORY_LABELS.get(key, key),
                "models": by_category[key],
            }
            for key in (
                "general_chat",
                "codex",
                "research",
                "audio",
                "embeddings",
                "other",
            )
            if key in by_category
        ],
        "count": len(models),
        "source": "Duke AI Gateway GET /v1/models",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "error": error,
        "deprecated": [
            {"id": mid, "notes": note} for mid, note in sorted(DEPRECATED_IDS.items())
        ],
    }
    _cache["fetched_at"] = now
    _cache["payload"] = payload
    return payload
