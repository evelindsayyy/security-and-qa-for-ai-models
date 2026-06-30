"""
Tests for scan browser launch — no subprocess spawn, no HF downloads.

  uv run python -m unittest unit_tests.test_scan_launch -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import scan_launch  # noqa: E402


class ValidateLaunchTest(unittest.TestCase):
    def test_valid_repo_passes(self) -> None:
        self.assertIsNone(scan_launch.validate_launch("gpt2"))
        self.assertIsNone(scan_launch.validate_launch("BAAI/bge-small-en-v1.5"))

    def test_empty_repo_rejected(self) -> None:
        err = scan_launch.validate_launch("   ")
        self.assertIn("enter a Hugging Face repo", err)

    def test_traversal_rejected(self) -> None:
        err = scan_launch.validate_launch("../evil")
        self.assertIn("invalid repo id", err)

    def test_absolute_path_rejected(self) -> None:
        err = scan_launch.validate_launch("/etc/passwd")
        self.assertIn("invalid repo id", err)

    def test_invalid_chars_rejected(self) -> None:
        err = scan_launch.validate_launch("org/model; rm -rf /")
        self.assertIn("use org/model", err)

    def test_all_scanners_disabled_rejected(self) -> None:
        err = scan_launch.validate_launch(
            "gpt2",
            skip_modelscan=True,
            skip_fickling=True,
            skip_modelaudit=True,
            skip_deps=True,
            skip_secrets=True,
        )
        self.assertIn("at least one scanner", err)


class BuildCommandTest(unittest.TestCase):
    def test_command_is_argv_list(self) -> None:
        cmd = scan_launch.build_command("gpt2")
        self.assertIsInstance(cmd, list)
        self.assertIn("-m", cmd)
        self.assertIn("scanner", cmd)
        self.assertIn("scan", cmd)
        self.assertIn("gpt2", cmd)

    def test_skip_flags_forwarded(self) -> None:
        cmd = scan_launch.build_command(
            "gpt2",
            skip_modelscan=True,
            skip_secrets=True,
        )
        self.assertIn("--skip-modelscan", cmd)
        self.assertIn("--skip-secrets", cmd)


class GetStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        patcher = mock.patch.object(scan_launch, "ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        out_patcher = mock.patch.object(scan_launch, "SCAN_OUTPUT", root / "scanner" / "output")
        out_patcher.start()
        self.addCleanup(out_patcher.stop)
        self.out = root / "scanner" / "output"

    def test_unsafe_slug_is_not_found(self) -> None:
        self.assertEqual(scan_launch.get_status("../../etc")["status"], "not_found")

    def test_complete_when_result_exists(self) -> None:
        slug = "gpt2"
        (self.out / slug).mkdir(parents=True)
        (self.out / slug / "scan_result.json").write_text("{}", encoding="utf-8")
        self.assertEqual(scan_launch.get_status(slug)["status"], "complete")

    def test_running_includes_log_tail(self) -> None:
        slug = "gpt2"
        out_slug = self.out / slug
        out_slug.mkdir(parents=True)
        log = out_slug / "scan_run.log"
        log.write_text("x" * 2000, encoding="utf-8")
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        scan_launch._RUNNING[slug] = fake_proc
        self.addCleanup(lambda: scan_launch._RUNNING.pop(slug, None))
        status = scan_launch.get_status(slug)
        self.assertEqual(status["status"], "running")
        self.assertGreater(len(status["message"]), 500)

    def test_validate_rejects_inflight(self) -> None:
        slug = "gpt2"
        lock = self.out / slug / "run.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        from dbutils import run_lock

        run_lock.try_acquire(lock, pid=os.getpid(), source=run_lock.FRONTEND_SOURCE)
        self.addCleanup(run_lock.release, lock)
        err = scan_launch.validate_launch("gpt2")
        self.assertIn("already running", err)


class LaunchRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_app({"TESTING": True}).test_client()

    def test_form_renders(self) -> None:
        r = self.client.get("/scans/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gpt2", r.data)

    def test_start_rejects_invalid_repo(self) -> None:
        r = self.client.post("/scans/start", data={"hf_repo": "../evil"})
        self.assertEqual(r.status_code, 400)

    def test_start_rejects_all_scanners_off(self) -> None:
        r = self.client.post("/scans/start", data={"hf_repo": "gpt2"})
        self.assertEqual(r.status_code, 400)

    def test_start_valid_spawns_and_redirects(self) -> None:
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 424242
        data = {
            "hf_repo": "gpt2",
            "run_modelscan": "on",
            "run_fickling": "on",
            "run_modelaudit": "on",
            "run_deps": "on",
            "run_secrets": "on",
        }
        with mock.patch("frontend.run_launch.try_lookup_reusable", return_value=None), \
             mock.patch.object(scan_launch.subprocess, "Popen", return_value=fake_proc) as popen:
            r = self.client.post("/scans/start", data=data)
        self.assertEqual(r.status_code, 302)
        self.assertIn("status=running", r.headers["Location"])
        popen.assert_called_once()
        argv = popen.call_args.args[0]
        self.assertIsInstance(argv, list)
        self.assertIn("gpt2", argv)

    def test_status_endpoint_returns_json(self) -> None:
        r = self.client.get("/scans/nonexistent-slug/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
