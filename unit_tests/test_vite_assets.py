"""Tests for frontend/vite_assets.py manifest resolution and dist serving.

Covers the two deployment modes and their failure modes:

1. VM (production): the working tree has no Vite build (gitignored, removed by
   deploy-remote.sh). Assets — including hashed filenames — must resolve from
   the image bake (/opt/frontend-dist), or the UI is unstyled / 404s.
2. Dev: run.sh rebuilds the working-tree build (frontend/static/dist) before
   start. That build reflects the source you just edited and MUST win over a
   possibly-stale image bake, or edits never show up.
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
    def test_reads_working_tree_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            _write_build(dist, "main-abc123.js", "main-abc123.css")
            with mock.patch.object(vite_assets, "_DIST", dist), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", Path("/nonexistent")):
                self.assertEqual(vite_assets.vite_entry(), "dist/assets/main-abc123.js")
                self.assertEqual(
                    vite_assets.vite_css_entries(), ["dist/assets/main-abc123.css"]
                )

    def test_falls_back_to_image_dist_when_working_tree_empty(self) -> None:
        """VM case: no working-tree build → serve the image bake."""
        with tempfile.TemporaryDirectory() as tmp:
            bind = Path(tmp) / "bind"  # empty, like VM after git pull + dist removal
            bind.mkdir()
            image = Path(tmp) / "image"
            _write_build(image, "main-fromimg.js", "main-fromimg.css")
            with mock.patch.object(vite_assets, "_DIST", bind), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", image):
                self.assertEqual(vite_assets.vite_entry(), "dist/assets/main-fromimg.js")

    def test_prefers_working_tree_build_over_image_bake(self) -> None:
        """Dev case: the working-tree build (your latest edits, rebuilt by
        run.sh) must win over a possibly-stale image bake — otherwise a
        docker-layer-cached /opt/frontend-dist serves outdated CSS/JS and your
        changes never appear."""
        with tempfile.TemporaryDirectory() as tmp:
            bind = Path(tmp) / "bind"
            _write_build(bind, "main-FRESHEDIT.js", "main-FRESHEDIT.css")
            image = Path(tmp) / "image"
            _write_build(image, "main-STALEIMAGE.js", "main-STALEIMAGE.css")
            with mock.patch.object(vite_assets, "_DIST", bind), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", image):
                self.assertEqual(
                    vite_assets.vite_entry(), "dist/assets/main-FRESHEDIT.js"
                )
                self.assertEqual(
                    vite_assets.vite_css_entries(), ["dist/assets/main-FRESHEDIT.css"]
                )

    def test_dev_fallback_when_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(vite_assets, "_DIST", Path(tmp) / "none"), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", Path(tmp) / "none2"):
                self.assertEqual(vite_assets.vite_entry(), "dist/main.js")
                self.assertEqual(vite_assets.vite_css_entries(), [])


class StaticDistServingTest(unittest.TestCase):
    """Browser requests hashed dist assets; they must resolve to real files."""

    def test_serves_hashed_assets_from_image_when_working_tree_empty(self) -> None:
        """VM case: hashed asset URLs come from the image manifest and the
        matching files must be served from the image bake."""
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
                self.assertEqual(client.get(f"/static/{entry}").status_code, 200)
                self.assertEqual(client.get(f"/static/{css}").status_code, 200)

    def test_serves_working_tree_content_over_image(self) -> None:
        """Dev case: the served bytes are the working-tree build, not the image."""
        with tempfile.TemporaryDirectory() as tmp:
            bind = Path(tmp) / "bind"
            _write_build(bind, "main-fresh.js", "main-fresh.css")
            (bind / "assets" / "main-fresh.js").write_text("// NEW fresh js", encoding="utf-8")
            image = Path(tmp) / "image"
            _write_build(image, "main-stale.js", "main-stale.css")
            (image / "assets" / "main-stale.js").write_text("// OLD stale js", encoding="utf-8")
            with mock.patch.object(vite_assets, "_DIST", bind), \
                 mock.patch.object(vite_assets, "_IMAGE_DIST", image):
                app = create_app({"TESTING": True})
                client = app.test_client()
                entry = vite_assets.vite_entry()
                self.assertIn("fresh", entry)
                resp = client.get(f"/static/{entry}")
                self.assertEqual(resp.status_code, 200)
                self.assertIn(b"NEW fresh js", resp.data)

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


class DockerfileTailwindContentTest(unittest.TestCase):
    """Guard against the image-bake staleness root cause.

    tailwind.config.js scans ../templates/**/*.html. If the Docker frontend-build
    stage doesn't copy frontend/templates into the build context, Tailwind purges
    every class used only in templates and the production (image-bake) UI renders
    unstyled. Lock in that the Dockerfile copies templates before `npm run build`.
    """

    def test_dockerfile_copies_templates_for_tailwind_scan(self) -> None:
        root = Path(__file__).resolve().parent.parent
        tw = (root / "frontend" / "assets" / "tailwind.config.js").read_text(
            encoding="utf-8"
        )
        if "templates" not in tw:
            self.skipTest("tailwind config no longer scans templates")

        dockerfile = (root / "docker" / "Dockerfile").read_text(encoding="utf-8")
        build_stage = dockerfile.split("FROM", 2)
        frontend_stage = next(
            (s for s in build_stage if "AS frontend-build" in s), ""
        )
        self.assertIn(
            "frontend/templates",
            frontend_stage,
            "Dockerfile frontend-build stage must COPY frontend/templates so "
            "Tailwind can scan them (else template-only classes are purged).",
        )
        idx_templates = frontend_stage.index("frontend/templates")
        idx_build = frontend_stage.index("npm run build")
        self.assertLess(
            idx_templates,
            idx_build,
            "templates must be copied before `npm run build`",
        )


if __name__ == "__main__":
    unittest.main()
