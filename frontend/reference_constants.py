"""Shared reference-model ordering for pillar comparison and reference tables."""

from __future__ import annotations

PREFERRED_REFERENCE_MODELS = ("GPT 4.1 Mini", "Llama 3.3")


def order_models(models: set[str] | list[str]) -> list[str]:
    """Preferred gateway models first, then alphabetical."""
    models_set = set(models)
    ordered = [m for m in PREFERRED_REFERENCE_MODELS if m in models_set]
    ordered.extend(sorted(models_set - set(ordered)))
    return ordered
