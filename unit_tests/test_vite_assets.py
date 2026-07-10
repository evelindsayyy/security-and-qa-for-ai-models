"""Tests for frontend/vite_assets.py manifest resolution."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import vite_assets


class ViteAssetsTest(unittest.TestCase):
    def setUp(self) -> None:
        vite_assets._manifest.cache_clear()

    def tearDown(self) -> None:
        vite_assets._manifest.cache_clear()

    def test_vite_entry_reads_bind_mounted_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp) / "dist"
            manifest_dir = dist / ".vite"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "src/main.ts": {
                            "file": "assets/main-abc123.js",
                            "css": ["assets/main-abc123.css"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(vite_assets, "_DIST", dist):
                with mock.patch.object(
                    vite_assets,
                    "_manifest_paths",
                    return_value=[manifest_dir / "manifest.json"],
                ):
                    self.assertEqual(vite_assets.vite_entry(), "dist/assets/main-abc123.js")
                    self.assertEqual(
                        vite_assets.vite_css_entries(),
                        ["dist/assets/main-abc123.css"],
                    )

    def test_vite_entry_falls_back_when_no_manifest(self) -> None:
        with mock.patch.object(vite_assets, "_manifest_paths", return_value=[]):
            self.assertEqual(vite_assets.vite_entry(), "dist/main.js")
            self.assertEqual(vite_assets.vite_css_entries(), [])

    def test_manifest_falls_back_to_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_manifest = Path(tmp) / ".vite" / "manifest.json"
            image_manifest.parent.mkdir(parents=True)
            image_manifest.write_text(
                json.dumps({"src/main.ts": {"file": "assets/main-from-image.js"}}),
                encoding="utf-8",
            )
            missing = Path(tmp) / "missing" / "manifest.json"
            with mock.patch.object(
                vite_assets,
                "_manifest_paths",
                return_value=[missing, image_manifest],
            ):
                self.assertEqual(vite_assets.vite_entry(), "dist/assets/main-from-image.js")


if __name__ == "__main__":
    unittest.main()
