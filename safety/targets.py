"""Target model and provider resolution for the safety pipeline.

This module keeps the model/provider mapping separate from the reusable
Promptfoo and Garak configuration templates.
"""

from __future__ import annotations

import os
from typing import Any


_DEFAULT_TARGET = {
    "provider_id": "openai:chat:GPT 4.1 Mini",
    "label": "duke-gpt-4.1-mini",
    "api_base_url": "https://litellm.oit.duke.edu/v1",
    "api_key_env": "OPENAI_API_KEY",
    "temperature": 0,
    "max_tokens": 300,
}


MODEL_TARGETS: dict[str, dict[str, Any]] = {
    "gpt-4.1-mini": {
        **_DEFAULT_TARGET,
        "model_id": "gpt-4.1-mini",
        "description": "Default Duke AI Gateway GPT-4.1 Mini target",
    },
    "default": {
        **_DEFAULT_TARGET,
        "model_id": "default",
        "description": "Fallback target configuration for safety runs",
    },
}


def resolve_target(model_id: str) -> dict[str, Any]:
    """Resolve a runtime target config for a model alias.

    The returned dictionary is intentionally small and serializable so the
    pipeline can inject it into both Promptfoo and Garak templates.
    """
    config = dict(MODEL_TARGETS.get(model_id, MODEL_TARGETS["default"]))
    config.setdefault("model_id", model_id)
    config.setdefault("api_key_env", "OPENAI_API_KEY")
    config.setdefault("temperature", 0)
    config.setdefault("max_tokens", 300)

    # Allow environment overrides to keep the runtime target flexible.
    if os.getenv("SAFETY_API_BASE_URL"):
        config["api_base_url"] = os.environ["SAFETY_API_BASE_URL"]
    if os.getenv("SAFETY_API_KEY_ENV"):
        config["api_key_env"] = os.environ["SAFETY_API_KEY_ENV"]
    if os.getenv("SAFETY_MODEL_LABEL"):
        config["label"] = os.environ["SAFETY_MODEL_LABEL"]

    return config


def available_targets() -> list[str]:
    return sorted(k for k in MODEL_TARGETS if k != "default")
