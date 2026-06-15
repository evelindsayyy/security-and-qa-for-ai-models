"""Apply pillar-specific loaders to Postgres (shared --apply path)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any


def jsonb_param(value: Any) -> str:
    """Serialize a Python value for ``%(name)s::jsonb`` INSERT parameters."""
    return json.dumps(value)


def apply_loader(
    dsn: str,
    load_fn: Callable[[Any], None],
    *,
    item_count: int,
    item_label: str = "item(s)",
) -> None:
    """Connect, call ``load_fn(conn)``, print success. ``load_fn`` must commit."""
    from dbutils.connection import connect

    with connect(dsn) as conn:
        load_fn(conn)
    print(
        f"Loaded {item_count} {item_label}. "
        "Re-running is safe when INSERTs use ON CONFLICT DO NOTHING."
    )


def exit_if_apply_without_dsn(dsn: str | None) -> None:
    if not dsn:
        sys.exit(
            "--apply needs a DSN: pass --dsn or set POSTGRES_DSN / DATABASE_URL "
            "(or EFFICACY_DB_DSN for efficacy)"
        )


def print_dry_run_hint() -> None:
    print("\nDry run (no database touched). Pass --apply with a DSN to load.")
