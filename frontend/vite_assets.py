"""Resolve Vite-built asset URLs and serve the built bundle.

There are two possible sources of the Vite build, with clear ownership:

- ``frontend/static/dist`` (``_DIST``) — the build for the *current working
  tree*. In local/dev runs, ``docker/run.sh`` (and ``main.py``) rebuild this on
  the host via ``scripts/build-frontend.sh`` immediately before starting, so it
  reflects whatever source you just edited. It is gitignored.
- ``/opt/frontend-dist`` (``_IMAGE_DIST``) — the build baked into the Docker
  image at image-build time. This is what production (the VM) serves, because
  a freshly cloned/pulled repo has no working-tree build.

Priority is therefore **working-tree build first, image bake as fallback**: in
dev you see your edits; on the VM (no working-tree build) you get the image's
baked assets. To keep this deterministic:

- ``deploy-remote.sh`` removes ``frontend/static/dist`` on the VM after git
  sync, so the VM never shadows the fresh image bake with a stale leftover.
- The entrypoint does NOT copy between the two (an earlier "seed once" step
  caused staleness — a bind mount seeded by an old image never refreshed).

Both the manifest lookup and the ``/static/dist`` file route resolve to the
*same* directory (``_active_dist_dir``), so the files the browser fetches always
match the manifest that generated their hashed URLs (no "split brain").
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import abort, send_from_directory

_DIST = Path(__file__).resolve().parent / "static" / "dist"
_IMAGE_DIST = Path("/opt/frontend-dist")
_ENTRY = "src/main.ts"


def _dist_dirs() -> list[Path]:
    """Candidate dist dirs, in priority order (working-tree build, then image).

    The working-tree build (``_DIST``) reflects the current source and is
    rebuilt before every dev start, so it wins. The image bake (``_IMAGE_DIST``)
    is the fallback used in production, where no working-tree build exists.
    """
    dirs = [_DIST]
    if _IMAGE_DIST != _DIST:
        dirs.append(_IMAGE_DIST)
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
    resolved active dist dir (working-tree build preferred, image bake fallback),
    so the files the browser fetches always match the manifest that produced
    their URLs — even when the working tree has no build (VM after git pull)."""

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
