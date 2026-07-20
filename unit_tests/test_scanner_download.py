"""Unit tests for scanner/download.py preflight and incomplete-dir handling."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scanner import download as download_mod


class DownloadCompleteMarkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.patcher = mock.patch.object(download_mod, "MODELS_ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.dir_patcher = mock.patch.object(
            download_mod, "model_dir", side_effect=lambda mid: self.root / mid.replace("/", "--")
        )
        self.dir_patcher.start()
        self.addCleanup(self.dir_patcher.stop)

    def test_incomplete_dir_is_not_complete(self) -> None:
        d = self.root / "org--model"
        d.mkdir()
        (d / "model.safetensors").write_bytes(b"x")
        self.assertFalse(download_mod.model_download_complete("org/model"))

    def test_clear_incomplete_removes_partial_tree(self) -> None:
        d = self.root / "org--model"
        d.mkdir()
        (d / "partial").write_text("x", encoding="utf-8")
        self.assertTrue(download_mod.clear_incomplete_model("org/model"))
        self.assertFalse(d.exists())

    def test_clear_incomplete_keeps_complete_tree(self) -> None:
        d = self.root / "org--model"
        d.mkdir()
        (d / download_mod._COMPLETE_MARKER).write_text("ok\n", encoding="utf-8")
        self.assertFalse(download_mod.clear_incomplete_model("org/model"))
        self.assertTrue(d.exists())


class DownloadPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.patcher = mock.patch.object(download_mod, "MODELS_ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.dir_patcher = mock.patch.object(
            download_mod, "model_dir", side_effect=lambda mid: self.root / mid.replace("/", "--")
        )
        self.dir_patcher.start()
        self.addCleanup(self.dir_patcher.stop)

    def test_refuses_when_disk_too_small(self) -> None:
        usage = mock.Mock(free=1_000_000_000)  # 1 GB free
        with mock.patch.object(
            download_mod, "_repo_download_bytes", return_value=(40_000_000_000, 17, False)
        ), mock.patch.object(download_mod.shutil, "disk_usage", return_value=usage):
            with self.assertRaises(download_mod.DownloadError) as ctx:
                download_mod._preflight("unsloth/big", token=None)
        self.assertIn("not enough free disk", str(ctx.exception))

    def test_refuses_when_over_max_gb(self) -> None:
        usage = mock.Mock(free=500_000_000_000)
        with mock.patch.dict("os.environ", {"SCAN_MAX_MODEL_GB": "20"}), mock.patch.object(
            download_mod, "_repo_download_bytes", return_value=(39_540_000_000, 17, False)
        ), mock.patch.object(download_mod.shutil, "disk_usage", return_value=usage):
            with self.assertRaises(download_mod.DownloadError) as ctx:
                download_mod._preflight("unsloth/big", token=None)
        self.assertIn("above the scan limit", str(ctx.exception))

    def test_gated_without_token_fails(self) -> None:
        with mock.patch.object(
            download_mod, "_repo_download_bytes", return_value=(1_000_000, 3, True)
        ):
            with self.assertRaises(download_mod.DownloadError) as ctx:
                download_mod._preflight("meta-llama/secret", token=None)
        self.assertIn("gated", str(ctx.exception).lower())

    def test_download_model_cleans_up_on_hub_failure(self) -> None:
        usage = mock.Mock(free=500_000_000_000)
        with mock.patch.object(download_mod, "_hub_token", return_value="tok"), mock.patch.object(
            download_mod, "_repo_download_bytes", return_value=(1_000_000, 2, False)
        ), mock.patch.object(download_mod.shutil, "disk_usage", return_value=usage), mock.patch.object(
            download_mod, "snapshot_download", side_effect=RuntimeError("429 Too Many Requests")
        ):
            with self.assertRaises(download_mod.DownloadError) as ctx:
                download_mod.download_model("org/model")
        self.assertIn("429", str(ctx.exception))
        self.assertFalse((self.root / "org--model").exists())


class FailedStatusMessageTest(unittest.TestCase):
    def test_prefers_error_lines(self) -> None:
        from frontend.log_status import _prefer_error_lines

        text = "Fetching 17 files\n" + ("x" * 100) + "\nERROR: not enough free disk\n"
        out = _prefer_error_lines(text)
        self.assertIn("ERROR: not enough free disk", out)


if __name__ == "__main__":
    unittest.main()
