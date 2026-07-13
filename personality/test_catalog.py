"""Metadata for personality tests.

Add a new key here when introducing another instrument later.
"""

from __future__ import annotations

from typing import Any

TESTS: dict[str, dict[str, Any]] = {
    "bfi": {
        "label": "BFI (Big Five)",
        "short_label": "BFI",
        "script": "bfi_test.py",
        "total_items": 44,
        "progress_label": "BFI personality",
        "legacy_glob": "bfi_*.json",
        "env_prefix": "BFI",
    },
}

DEFAULT_TEST_KEY = "bfi"


def validate_test_key(test_key: str) -> str | None:
    key = (test_key or "").strip().lower()
    if key not in TESTS:
        return f"unknown personality test: {test_key!r}"
    return None


def get_test(test_key: str) -> dict[str, Any]:
    return TESTS[test_key.strip().lower()]
