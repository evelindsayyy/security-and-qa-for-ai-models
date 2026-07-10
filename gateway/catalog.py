"""
Live Duke AI Gateway model catalog — the single source of truth for which
models exist on the gateway right now.

Calls the OpenAI-compatible ``GET /v1/models`` endpoint (same base URL + key as
``evaluator/_gateway.py``) and caches the result briefly so pages and dropdowns
do not hammer the gateway. Every consumer that needs "all gateway models"
(frontend ``/models``, the safety + eval launch dropdowns, the ``python -m
gateway`` CLI) reads from here, so model ids are never hardcoded.

Refresh model:
- Auto: cached for ``_CACHE_TTL_SEC``; the next read after expiry re-fetches.
- Manual: ``get_gateway_catalog(force_refresh=True)`` (wired to the UI refresh
  button) re-fetches immediately.

Week 5+: this stays the live source; the Postgres ``models`` table is seeded
from the same ``GET /v1/models`` payload (see ``docs/data-model.md``).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load repo-root .env so the CLI works from any cwd (frontend already loads it
# at app startup; override=False keeps real env vars authoritative).
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_CACHE_TTL_SEC = 300
_cache: dict[str, Any] = {"fetched_at": 0.0, "payload": None}

# Team notes keyed by exact LiteLLM id (shown on /models). Keep concise.
ANNOTATIONS: dict[str, str] = {
    # General chat — OpenAI GPT-4.1
    "GPT 4.1": "Full-size GPT-4.1 chat; balanced quality and cost",
    "GPT 4.1 Mini": "Low-cost chat; good for smoke tests, benchmarks, and pilots",
    "GPT 4.1 Nano": "Smallest GPT-4.1 tier; cheapest OpenAI chat option",
    # General chat — OpenAI GPT-5 family
    "gpt-5": "Base GPT-5; reasoning-oriented, not always chat-tuned",
    "gpt-5-chat": "GPT-5 chat-tuned; strong default for efficacy and safety pilots",
    "gpt-5-mini": "Compact GPT-5 reasoning; low cost — may need higher max_tokens",
    "gpt-5-nano": "Lowest-cost GPT-5 family chat",
    "gpt-5.1": "GPT-5.1 base model",
    "gpt-5.1-chat": "GPT-5.1 chat variant",
    "gpt-5.2": "GPT-5.2 base model",
    "gpt-5.2-chat": "GPT-5.2 chat variant",
    "gpt-5.3-chat": "GPT-5.3 chat variant",
    "gpt-5.4": "GPT-5.4 flagship chat",
    "gpt-5.4-mini": "Mid-tier GPT-5.4 chat; lower cost than full 5.4",
    "gpt-5.4-nano": "Budget GPT-5.4 chat tier",
    "gpt-5.4-pro": "Premium GPT-5.4; highest capability, highest cost",
    "gpt-5.5": "Latest GPT-5.5 generation chat",
    "gpt-oss-120b": "Open-weight–style 120B model served via cloud API",
    # General chat — Meta Llama
    "Llama 3.3": "Meta Llama 3.3 70B-class chat; prior generation, still capable",
    "Llama 4 Maverick": "Meta Llama 4 flagship; strong chat and common eval judge",
    "Llama 4 Scout": "Compact Llama 4 chat; lower cost Meta option",
    # Codex / agentic coding
    "gpt-5-codex": "GPT-5 agentic coding model",
    "gpt-5.1-codex": "GPT-5.1 coding agent",
    "gpt-5.1-codex-max": "Largest GPT-5.1 Codex tier for complex coding",
    "gpt-5.1-codex-mini": "Budget Codex tier for lighter coding tasks",
    "gpt-5.2-codex": "GPT-5.2 coding agent",
    "gpt-5.3-codex": "GPT-5.3 coding agent",
    # Research / reasoning
    "o3-deep-research": "Deep research agent; slow and expensive — avoid bulk runs",
    "o4 Mini": "Compact o4 reasoning model (capital M in Mini)",
    "o4-mini-deep-research": "Lower-cost deep-research variant",
    # Audio
    "gpt-4o-transcribe": "GPT-4o speech-to-text transcription",
    "gpt-4o-transcribe-diarize": "Transcription with speaker diarization",
    "whisper-1": "Whisper ASR; general speech-to-text",
    # Embeddings
    "text-embedding-3-small": "Small embedding model for retrieval and RAG",
    "text-embedding-3-large": "Higher-quality embeddings; larger vectors",
}

# Fallback when the gateway adds a model before we annotate it explicitly.
_CATEGORY_DEFAULT_NOTES: dict[str, str] = {
    "general_chat": "General-purpose chat model on the Duke gateway",
    "codex": "Agentic coding model — use for software-engineering tasks",
    "research": "Research or deep-reasoning model — higher latency and cost",
    "audio": "Audio or transcription model — not for chat eval",
    "embeddings": "Embedding model — vector search, not chat",
    "other": "Gateway model — see OIT docs for intended use",
}


def _notes_for(model_id: str, category: str) -> str:
    explicit = ANNOTATIONS.get(model_id)
    if explicit:
        return explicit
    return _CATEGORY_DEFAULT_NOTES.get(category, _CATEGORY_DEFAULT_NOTES["other"])


# Pricing: single source of truth is the evaluator's cost table
# (evaluator/runner.py:_COST_PER_M_TOKENS, USD per 1M (input, output) tokens).
# Lazily imported + cached so the catalog page doesn't pull the evaluator
# stack at app startup; {} if unavailable. Partial coverage — priced chat
# models only; everything else simply shows no price.
_pricing_cache: dict[str, tuple[float, float]] | None = None


def _pricing_table() -> dict[str, tuple[float, float]]:
    global _pricing_cache
    if _pricing_cache is not None:
        return _pricing_cache
    try:
        import sys
        from pathlib import Path

        evaluator = Path(__file__).resolve().parent.parent / "evaluator"
        if str(evaluator) not in sys.path:
            sys.path.insert(0, str(evaluator))
        from runner import _COST_PER_M_TOKENS

        _pricing_cache = dict(_COST_PER_M_TOKENS)
    except Exception:  # noqa: BLE001 — pricing is optional decoration
        _pricing_cache = {}
    return _pricing_cache


# Why a live model shows "—" instead of a token price. Two reasons:
#   * it's priced in a unit the (input, output)/1M-token table can't express
#     (audio per-minute, embeddings input-only, rerank per-search), or
#   * it isn't on Duke's published rate sheet (kb0038832) yet.
# Keyed by exact id first, then by category as a fallback, so the catalog
# EXPLAINS every blank price instead of looking half-filled. Surfaced only when
# a model has no token rate (a priced model never shows a note).
_PRICE_NOTE_BY_ID: dict[str, str] = {
    "whisper-1": "billed per audio-minute ($0.006/min), not per token",
    "text-embedding-3-small": "input-only: $0.02 per 1M tokens (no output cost)",
    "text-embedding-3-large": "input-only: $0.13 per 1M tokens (no output cost)",
    "Cohere-rerank-v4.0-fast": "rerank — priced per search, not per token",
    "Cohere-rerank-v4.0-pro": "rerank — priced per search, not per token",
}
_PRICE_NOTE_BY_CATEGORY: dict[str, str] = {
    "embeddings": "input-only pricing; no per-token output cost",
    "audio": "billed per audio-minute, not per token",
}


def _price_note_for(model_id: str, category: str) -> str | None:
    """Reason a model has no token price, or None if it's priced."""
    return _PRICE_NOTE_BY_ID.get(model_id) or _PRICE_NOTE_BY_CATEGORY.get(category)

# Legacy aliases from week-2 spikes (not returned by /v1/models anymore).
DEPRECATED_IDS: dict[str, str] = {
    "Mistral on-site": "deprecated — phased out; not on gateway allowlist",
}

# Categories whose models can drive chat-based safety / efficacy runs.
CHAT_CATEGORIES: frozenset[str] = frozenset({"general_chat", "codex", "research"})

_CATEGORY_LABELS = {
    "general_chat": "General chat (safety + efficacy)",
    "codex": "Codex / agentic coding",
    "audio": "Audio / transcription",
    "embeddings": "Embeddings",
    "research": "Research / reasoning",
    "other": "Other",
}

_CATEGORY_ORDER = (
    "general_chat",
    "codex",
    "research",
    "audio",
    "embeddings",
    "other",
)


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
    if (
        model_id in ("GPT 4.1", "GPT 4.1 Mini", "GPT 4.1 Nano")
        or lower.startswith("gpt-5")
        or lower.startswith("gpt-oss")
        or model_id.startswith("Llama")
    ):
        return "general_chat"
    return "other"


def _fetch_live_models() -> tuple[list[dict[str, str]], str | None]:
    """Return (rows, error). Rows sorted by category label then id."""
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
    except Exception as exc:  # noqa: BLE001 — surface in UI/CLI, never crash
        return [], f"Gateway models.list failed: {type(exc).__name__}: {exc}"

    prices = _pricing_table()
    rows: list[dict[str, Any]] = []
    for item in response.data:
        mid = item.id
        cat = _categorize(mid)
        rate = prices.get(mid)  # (input, output) USD per 1M tokens, or None
        rows.append(
            {
                "id": mid,
                "category": cat,
                "notes": _notes_for(mid, cat),
                "owned_by": getattr(item, "owned_by", "") or "",
                "price_in": rate[0] if rate else None,
                "price_out": rate[1] if rate else None,
                "price_note": None if rate else _price_note_for(mid, cat),
            }
        )

    rows.sort(key=lambda r: (_CATEGORY_LABELS.get(r["category"], r["category"]), r["id"]))
    return rows, None


def get_gateway_catalog(*, force_refresh: bool = False) -> dict[str, Any]:
    """
    Cached gateway catalog for templates and launch dropdowns.

    Returns a dict with: has_models, models (flat list), by_category (grouped),
    count, source, fetched_at (iso or None), error (str or None), deprecated.
    """
    now = time.time()
    if (
        not force_refresh
        and _cache["payload"] is not None
        and now - _cache["fetched_at"] < _CACHE_TTL_SEC
    ):
        return _cache["payload"]

    models, error = _fetch_live_models()
    by_category: dict[str, list[dict[str, Any]]] = {}
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
            for key in _CATEGORY_ORDER
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


def list_model_ids(*, force_refresh: bool = False) -> list[str]:
    """Flat list of every live gateway model id (sorted by category then id)."""
    return [m["id"] for m in get_gateway_catalog(force_refresh=force_refresh)["models"]]


def eligible_models(
    categories: frozenset[str] = CHAT_CATEGORIES, *, force_refresh: bool = False
) -> list[str]:
    """Live model ids whose category is in ``categories`` (e.g. chat-capable)."""
    return [
        m["id"]
        for m in get_gateway_catalog(force_refresh=force_refresh)["models"]
        if m.get("category") in categories
    ]
