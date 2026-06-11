"""Target model and provider resolution for the safety pipeline.

This module keeps the model/provider mapping separate from the reusable
Promptfoo and Garak configuration templates.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=False)


_DEFAULT_TARGET = {
    "provider_id": "openai:chat:{model_id}",
    "label": "{model_id}",
    "api_base_url": "https://litellm.oit.duke.edu/v1",
    "api_key_env": "DUKE_GATEWAY_KEY",
    "temperature": 0,
    "max_tokens": 300,
}


_CACHE_TTL_SEC = 300
_models_cache: dict[str, Any] = {"fetched_at": 0.0, "models": None}


# Snapshot from docs/gateway-models.md. The live Gateway catalog is preferred
# whenever credentials are available, but this keeps local/offline resolution
# from falling back to the wrong model.
DOCUMENTED_GATEWAY_MODELS = [
    "GPT 4.1",
    "GPT 4.1 Mini",
    "GPT 4.1 Nano",
    "gpt-5",
    "gpt-5-chat",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5.1",
    "gpt-5.1-chat",
    "gpt-5.2",
    "gpt-5.2-chat",
    "gpt-5.3-chat",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.5",
    "gpt-oss-120b",
    "Llama 3.3",
    "Llama 4 Maverick",
    "Llama 4 Scout",
    "gpt-5-codex",
    "gpt-5.1-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
    "gpt-5.2-codex",
    "gpt-5.3-codex",
    "o3-deep-research",
    "o4 Mini",
    "o4-mini-deep-research",
    "gpt-5.4-pro",
    "gpt-4o-transcribe",
    "gpt-4o-transcribe-diarize",
    "whisper-1",
    "text-embedding-3-small",
    "text-embedding-3-large",
]


ALIASES: dict[str, str] = {
    "default": "GPT 4.1 Mini",
    "gpt41mini": "GPT 4.1 Mini",
    "gpt-4.1-mini": "GPT 4.1 Mini",
    "gpt 4.1 mini": "GPT 4.1 Mini",
    "gpt41": "GPT 4.1",
    "gpt-4.1": "GPT 4.1",
    "gpt 4.1": "GPT 4.1",
    "llama-3.3": "Llama 3.3",
    "llama 3.3": "Llama 3.3",
    "llama-4-maverick": "Llama 4 Maverick",
    "llama 4 maverick": "Llama 4 Maverick",
    "llama-4-scout": "Llama 4 Scout",
    "llama 4 scout": "Llama 4 Scout",
    "o4-mini": "o4 Mini",
    "o4 mini": "o4 Mini",
}


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _gateway_credentials() -> tuple[str, str | None, str | None]:
    url = (
        os.environ.get("SAFETY_API_BASE_URL")
        or os.environ.get("DUKE_GATEWAY_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("DUKE_GATEWAY_BASE_URL")
        or _DEFAULT_TARGET["api_base_url"]
    )

    if os.getenv("SAFETY_API_KEY_ENV"):
        key_env = os.environ["SAFETY_API_KEY_ENV"]
        return url, key_env, os.environ.get(key_env)

    for key_env in ("DUKE_GATEWAY_KEY", "OPENAI_API_KEY", "DUKE_AI_GATEWAY_API_KEY"):
        key = os.environ.get(key_env)
        if key:
            return url, key_env, key

    return url, "DUKE_GATEWAY_KEY", None


def _fetch_live_gateway_models(*, force_refresh: bool = False) -> list[str]:
    now = time.time()
    cached = _models_cache["models"]
    if (
        not force_refresh
        and cached is not None
        and now - _models_cache["fetched_at"] < _CACHE_TTL_SEC
    ):
        return list(cached)

    url, _key_env, key = _gateway_credentials()
    if not key:
        return []

    try:
        from openai import OpenAI

        client = OpenAI(base_url=url, api_key=key)
        response = client.models.list()
    except Exception:
        return []

    models = sorted({item.id for item in response.data})
    _models_cache["fetched_at"] = now
    _models_cache["models"] = models
    return models


def _resolve_model_id(model_id: str) -> tuple[str, str]:
    requested = model_id.strip()
    if not requested:
        requested = "default"

    alias_target = ALIASES.get(requested.lower())
    if alias_target:
        return alias_target, "alias"

    live_models = _fetch_live_gateway_models()
    for candidate in live_models:
        if requested == candidate:
            return candidate, "live_exact"
    requested_norm = _normalized(requested)
    for candidate in live_models:
        if requested_norm == _normalized(candidate):
            return candidate, "live_normalized"

    for candidate in DOCUMENTED_GATEWAY_MODELS:
        if requested == candidate:
            return candidate, "documented_exact"
    for candidate in DOCUMENTED_GATEWAY_MODELS:
        if requested_norm == _normalized(candidate):
            return candidate, "documented_normalized"

    return requested, "dynamic_unverified"


def _build_target(model_id: str, *, resolution_source: str) -> dict[str, Any]:
    url, key_env, _key = _gateway_credentials()
    return {
        "model_id": model_id,
        "provider_id": f"openai:chat:{model_id}",
        "label": model_id,
        "api_base_url": url,
        "api_key_env": key_env or "DUKE_GATEWAY_KEY",
        "temperature": _DEFAULT_TARGET["temperature"],
        "max_tokens": _DEFAULT_TARGET["max_tokens"],
        "description": f"Duke AI Gateway target ({resolution_source})",
        "resolution_source": resolution_source,
    }


def resolve_target(model_id: str) -> dict[str, Any]:
    """Resolve a runtime target config for a model alias.

    The returned dictionary is intentionally small and serializable so the
    pipeline can inject it into both Promptfoo and Garak templates.
    """
    gateway_model_id, resolution_source = _resolve_model_id(model_id)
    config = _build_target(gateway_model_id, resolution_source=resolution_source)

    # Allow environment overrides to keep the runtime target flexible.
    if os.getenv("SAFETY_MODEL_LABEL"):
        config["label"] = os.environ["SAFETY_MODEL_LABEL"]
    if os.getenv("SAFETY_PROVIDER_ID"):
        config["provider_id"] = os.environ["SAFETY_PROVIDER_ID"]
    if os.getenv("SAFETY_TEMPERATURE"):
        config["temperature"] = float(os.environ["SAFETY_TEMPERATURE"])
    if os.getenv("SAFETY_MAX_TOKENS"):
        config["max_tokens"] = int(os.environ["SAFETY_MAX_TOKENS"])

    return config


def available_targets() -> list[str]:
    models = _fetch_live_gateway_models()
    if not models:
        models = DOCUMENTED_GATEWAY_MODELS
    return sorted(models)
