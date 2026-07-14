"""Per-pillar read-path diagnostics for /api/health and operators."""

from __future__ import annotations

from typing import Any

_PILLARS: tuple[tuple[str, str, str, str], ...] = (
    ("scan", "frontend.scan_db_data", "get_scans_data_db", "scans"),
    ("safety", "frontend.safety_db_data", "get_safety_data_db", "models"),
    ("eval", "frontend.eval_db_data", "get_runs_data_db", "runs"),
    ("benchmark", "frontend.benchmark_db_data", "get_benchmarks_data_db", "runs"),
)


def pillar_read_diagnostics() -> dict[str, Any]:
    """Return per-pillar Postgres availability, row counts, and last fallback error."""
    from frontend.db_fallback import last_db_fallback_error

    out: dict[str, Any] = {}
    for name, mod_path, fn_name, row_key in _PILLARS:
        entry: dict[str, Any] = {"db_available": False, "source": "disk", "row_count": None}
        try:
            import importlib

            mod = importlib.import_module(mod_path)
            entry["db_available"] = bool(mod.available())
            if entry["db_available"]:
                data = getattr(mod, fn_name)()
                entry["source"] = "postgres"
                entry["row_count"] = len(data.get(row_key) or [])
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            entry["source"] = "error"
        out[name] = entry

    err = last_db_fallback_error()
    if err:
        out["last_fallback_error"] = err
    return out
