"""Shared Duke AI Gateway model catalog (live, cached single source of truth)."""

from gateway.catalog import (
    CHAT_CATEGORIES,
    eligible_models,
    get_gateway_catalog,
    list_model_ids,
)

__all__ = [
    "CHAT_CATEGORIES",
    "eligible_models",
    "get_gateway_catalog",
    "list_model_ids",
]
