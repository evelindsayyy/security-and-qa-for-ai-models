"""Resolve Vite-built asset URLs and serve the built bundle.

The Vite build output (``frontend/static/dist``) is gitignored, so a
bind-mounted repo on the VM has no build after ``git pull``. The Docker image
bakes a copy at ``/opt/frontend-dist`` from the *current* source on every
``docker build``, so it is always fresh for whatever image is running.

Two bugs to avoid:

1. "Split brain" — reading the manifest from one location while Flask serves
   files from another. Both the manifest lookup and the ``/static/dist`` file
   route resolve to the *same* directory.
2. Staleness — the entrypoint seeds the bind mount from the image once (only
   when the bind mount has no manifest at all), so a bind mount seeded by an
   older image build never gets refreshed by later image builds. The image
   bake is therefore preferred whenever it exists; the bind-mounted dist is
   only used as a fallback for bare-metal (non-Docker) host dev where
   ``/opt/frontend-dist`` doesn't exist.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import abort, send_from_directory

_DIST = Path(__file__).resolve().parent / "static" / "dist"
_IMAGE_DIST = Path("/opt/frontend-dist")
_ENTRY = "src/main.ts"


def _dist_dirs() -> list[Path]:
    """Candidate dist dirs, in priority order.

    The image bake is always fresh for the running image's source, so it is
    preferred over a bind-mounted dist, which may have been seeded once from
    an older image build and never refreshed. The bind mount is only relied
    on for bare-metal (non-Docker) host dev, where the image path is absent.
    """
    dirs = []
    if _IMAGE_DIST != _DIST:
        dirs.append(_IMAGE_DIST)
    dirs.append(_DIST)
    return dirs


def _active_dist_dir() -> Path:
    """The dist dir whose manifest we read AND whose files we serve.

    Not cached: on the VM a host build can populate the bind-mounted dist
    after the process starts, and the resolution is cheap.
    """
    for d in _dist_dirs():
        if (d / ".vite" / "manifest.json").is_file():
            return d
    return _DIST


def _manifest() -> dict:
    path = _active_dist_dir() / ".vite" / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
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
    """Expose asset helpers to Jinja templates and serve /static/dist files.

    A dedicated ``/static/dist/<path>`` route serves the built bundle from the
    resolved active dist dir (bind mount preferred, image bake fallback), so the
    files the browser fetches always match the manifest that produced their URLs
    — even when the bind-mounted repo has no build (VM after git pull)."""

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

    # More specific than Flask's built-in /static/<path>, so it wins for dist.
    @app.route("/static/dist/<path:filename>")
    def static_dist(filename: str):
        # Per-file resolution: prefer the active dist dir, but fall back to any
        # candidate that actually has the file (covers a stale bind-mount
        # manifest whose assets never landed).
        active = _active_dist_dir()
        for base in [active, *(_dist_dirs())]:
            if (base / filename).is_file():
                return send_from_directory(str(base), filename)
        abort(404)
