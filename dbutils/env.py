"""Repo-root .env loading and DSN resolution for ingest + read paths."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# dbutils/ -> repo root
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_repo_env() -> None:
    """Load ``<repo>/.env`` once. Shell-exported vars take precedence."""
    load_dotenv(REPO_ROOT / ".env", override=False)


def resolve_dsn(
    *env_keys: str,
    fallback_keys: tuple[str, ...] = ("DATABASE_URL",),
) -> str | None:
    """First non-empty DSN from ``env_keys``, then ``fallback_keys``."""
    for key in (*env_keys, *fallback_keys):
        value = os.environ.get(key)
        if value:
            return value
    return None
