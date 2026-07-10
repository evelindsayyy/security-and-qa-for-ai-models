"""Resolve Vite-built asset URLs from the manifest."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DIST = Path(__file__).resolve().parent / "static" / "dist"
_IMAGE_DIST = Path("/opt/frontend-dist")
_ENTRY = "src/main.ts"


def _manifest_paths() -> list[Path]:
    """Prefer bind-mounted dist; fall back to the image bake path."""
    paths = [_DIST / ".vite" / "manifest.json"]
    if _IMAGE_DIST != _DIST:
        paths.append(_IMAGE_DIST / ".vite" / "manifest.json")
    return paths


@lru_cache(maxsize=1)
def _manifest() -> dict:
    for path in _manifest_paths():
        if not path.is_file():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def vite_entry() -> str:
    """Primary JS bundle path under /static/."""
    manifest = _manifest()
    item = manifest.get(_ENTRY, {})
    file_name = item.get("file")
    if file_name:
        return f"dist/{file_name}"
    # Dev / CI fallback before first build
    return "dist/main.js"


def vite_css_entries() -> list[str]:
    manifest = _manifest()
    item = manifest.get(_ENTRY, {})
    css_files = item.get("css") or []
    return [f"dist/{name}" for name in css_files]


def register_vite_template_globals(app) -> None:
    """Expose asset helpers to Jinja templates."""

    @app.context_processor
    def _vite_context():
        return {
            "vite_entry": vite_entry(),
            "vite_css_entries": vite_css_entries(),
        }

    @app.template_global("vite_asset")
    def vite_asset(entry: str = _ENTRY) -> str:
        manifest = _manifest()
        item = manifest.get(entry, {})
        file_name = item.get("file")
        return f"dist/{file_name}" if file_name else "dist/main.js"
