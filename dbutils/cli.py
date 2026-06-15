"""Shared argparse flags for pillar ingest CLIs."""

from __future__ import annotations

import argparse

from dbutils.env import resolve_dsn

# Prefer a single POSTGRES_DSN for new pillars; EFFICACY_DB_DSN kept for eval.
DEFAULT_DSN_ENV_KEYS: tuple[str, ...] = (
    "POSTGRES_DSN",
    "DATABASE_URL",
    "EFFICACY_DB_DSN",
)


def add_ingest_arguments(
    parser: argparse.ArgumentParser,
    *,
    dsn_env_keys: tuple[str, ...] = DEFAULT_DSN_ENV_KEYS,
) -> None:
    """Add ``--apply`` and ``--dsn`` (default from env) to a pillar loader parser."""
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write to Postgres (default: dry run, no database connection)",
    )
    parser.add_argument(
        "--dsn",
        default=resolve_dsn(*dsn_env_keys),
        help=f"Postgres DSN (or set {' / '.join(dsn_env_keys)})",
    )
