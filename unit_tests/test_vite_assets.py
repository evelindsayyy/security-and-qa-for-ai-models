"""Tests for frontend/vite_assets.py manifest resolution and dist serving.

Reproduces the VM failure mode: a bind-mounted repo with no Vite build, where
the manifest + built files must be served from the image bake (/opt/frontend-dist)
so the UI keeps its styling.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import create_app, vite_assets


def _write_build(dist_dir: Path, js: str, css: str) -> None:
    (dist_dir / ".vite").mkdir(parents=True, exist_ok=True)
    (dist_dir / "assets").mkdir(parents=True, exist_ok=True)
    (dist_dir / ".vite" / "manifest.json").write_text(
        json.dumps({"src/main.ts": {"file": f"assets/{js}", "css": [f"assets/{css}"]}}),
        encoding="utf-8",
    )
    (dist_dir / "assets" / js).write_text("// js", encoding="utf-8")
    (dist_dir / "assets" / css).write_text("/* css */", encoding="utf-8")


class ViteEntryTest(unittest.TestCase):
    def test_reads_bind_mounted_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            _write_build(dist, "main-abc123.js", "main-abc123.css")
            with mock.patch.object(vite_assets, "_DIST", dist), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", Path("/nonexistent")):
                self.assertEqual(vite_assets.vite_entry(), "dist/assets/main-abc123.js")
                self.assertEqual(
                    vite_assets.vite_css_entries(), ["dist/assets/main-abc123.css"]
                )

    def test_falls_back_to_image_dist_when_bind_mount_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bind = Path(tmp) / "bind"  # empty, like VM after git pull
            bind.mkdir()
            image = Path(tmp) / "image"
            _write_build(image, "main-fromimg.js", "main-fromimg.css")
            with mock.patch.object(vite_assets, "_DIST", bind), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", image):
                self.assertEqual(vite_assets.vite_entry(), "dist/assets/main-fromimg.js")

    def test_dev_fallback_when_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(vite_assets, "_DIST", Path(tmp) / "none"), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", Path(tmp) / "none2"):
                self.assertEqual(vite_assets.vite_entry(), "dist/main.js")
                self.assertEqual(vite_assets.vite_css_entries(), [])


class StaticDistServingTest(unittest.TestCase):
    """The exact VM bug: browser requests hashed dist assets that must resolve."""

    def test_serves_hashed_assets_from_image_when_bind_mount_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bind = Path(tmp) / "bind"
            bind.mkdir()
            image = Path(tmp) / "image"
            _write_build(image, "main-xyz789.js", "main-xyz789.css")
            with mock.patch.object(vite_assets, "_DIST", bind), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", image):
                app = create_app({"TESTING": True})
                client = app.test_client()

                entry = vite_assets.vite_entry()  # dist/assets/main-xyz789.js
                css = vite_assets.vite_css_entries()[0]
                r_js = client.get(f"/static/{entry}")
                r_css = client.get(f"/static/{css}")
                self.assertEqual(r_js.status_code, 200, "hashed JS must be served")
                self.assertEqual(r_css.status_code, 200, "hashed CSS must be served")

    def test_missing_asset_404s(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bind = Path(tmp) / "bind"
            bind.mkdir()
            with mock.patch.object(vite_assets, "_DIST", bind), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", Path(tmp) / "none"):
                app = create_app({"TESTING": True})
                client = app.test_client()
                self.assertEqual(
                    client.get("/static/dist/assets/does-not-exist.js").status_code, 404
                )


if __name__ == "__main__":
    unittest.main()
