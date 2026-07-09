"""Build comparison heatmap payloads for Preact islands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_heatmap_payload(
    comparison_models: list[str],
    comparison_rows: list[dict[str, Any]],
    *,
    cell_url: Callable[[dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    rows_out: list[dict[str, Any]] = []
    for row in comparison_rows:
        cells_out: dict[str, Any] = {}
        for model in comparison_models:
            cell = (row.get("cells") or {}).get(model)
            if not cell:
                continue
            out = {
                "display": cell.get("display", "—"),
                "score_class": cell.get("score_class", ""),
            }
            if cell_url:
                url = cell_url(cell)
                if url:
                    out["slug"] = url
            cells_out[model] = out
        rows_out.append(
            {
                "key": row.get("key", ""),
                "label": row.get("label", ""),
                "badge_class": row.get("badge_class", ""),
                "cells": cells_out,
            }
        )
    return {"models": comparison_models, "rows": rows_out}
