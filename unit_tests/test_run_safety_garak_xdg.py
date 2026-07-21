"""Garak XDG env: shared HF cache, per-slug HOME."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from safety.run import garak_xdg_env, reclaim_legacy_per_slug_garak_xdg


class GarakXdgEnvSharedCacheTest(unittest.TestCase):
    def test_garak_xdg_env_sets_home_and_shared_cache(self) -> None:
        env = garak_xdg_env("unit-test-slug")
        self.assertIn("HOME", env)
        self.assertIn("XDG_CACHE_HOME", env)
        self.assertIn("unit-test-slug", env["HOME"])
        self.assertTrue(env["XDG_CACHE_HOME"].endswith(".garak-cache"))
        self.assertNotIn("unit-test-slug", env["XDG_CACHE_HOME"])
        self.assertNotIn("unit-test-slug", env["XDG_DATA_HOME"])
        self.assertEqual(env["USER"], "garak")
        self.assertEqual(env["LOGNAME"], "garak")

    def test_reclaim_legacy_per_slug_garak_xdg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug = root / "some-model"
            (slug / ".garak-cache").mkdir(parents=True)
            (slug / ".garak-data").mkdir(parents=True)
            (slug / "report.json").write_text("{}", encoding="utf-8")
            shared = root / ".garak-cache"
            shared.mkdir()
            self.assertEqual(reclaim_legacy_per_slug_garak_xdg(output_root=root), 2)
            self.assertFalse((slug / ".garak-cache").exists())
            self.assertFalse((slug / ".garak-data").exists())
            self.assertTrue((slug / "report.json").is_file())
            self.assertTrue(shared.is_dir())


if __name__ == "__main__":
    unittest.main()
