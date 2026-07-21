"""
Tests for scan browser launch — no subprocess spawn, no HF downloads.

  uv run python -m unittest unit_tests.test_scan_launch -v
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import run_paths  # noqa: E402
from frontend import scan_launch  # noqa: E402


def _isolate_scan_output(test_case: unittest.TestCase) -> Path:
    """Redirect scan_launch's module-level output paths to a scratch tempdir
    and reset its in-memory run registries, for any test that exercises the
    real (unmocked) launch path — i.e. hits ``/scans/start`` with only
    ``subprocess.Popen`` mocked out.

    Without this, a "launch" still writes a real run.lock under the repo's
    own scanner/output/<slug>/ and sets scan_launch._RUNNING[<slug>] for
    real. Both are module-global state shared by every test in the process,
    and start_run()'s cleanup of them runs on an unsynchronized background
    thread — so a later test that checks "is <slug> already running" can
    intermittently see this test's mock process as still in flight (this
    caused a real, intermittent CI failure).
    """
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    for attr, value in (
        ("ROOT", root),
        ("SCAN_OUTPUT", root / "scanner" / "output"),
        ("DOCKER_COMPOSE_FILE", root / "scanner" / "docker" / "compose.yml"),
    ):
        patcher = mock.patch.object(scan_launch, attr, value)
        patcher.start()
        test_case.addCleanup(patcher.stop)
    test_case.addCleanup(scan_launch._RUNNING.clear)
    test_case.addCleanup(scan_launch._INFLIGHT.clear)
    return root


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

    def test_stale_log_kills_hung_scan(self) -> None:
        slug = "hung-model"
        out_slug = self.out / slug
        out_slug.mkdir(parents=True)
        log = out_slug / "scan_run.log"
        log.write_text("Fetching 17 files: 47%\n", encoding="utf-8")
        # Make mtime look hours old
        old = time.time() - (50 * 60)
        os.utime(log, (old, old))
        fake_proc = mock.Mock()
        fake_proc.poll.side_effect = [None, 143]
        fake_proc.returncode = 143
        fake_proc.pid = 99999
        fake_proc.wait.return_value = 143
        scan_launch._RUNNING[slug] = fake_proc
        self.addCleanup(lambda: scan_launch._RUNNING.pop(slug, None))
        with mock.patch.object(scan_launch, "_terminate_scan_process") as term:
            with mock.patch.dict(os.environ, {"SCAN_STALL_SECONDS": "600"}):
                status = scan_launch.get_status(slug)
        term.assert_called_once()
        self.assertEqual(status["status"], "failed")
        self.assertIn("download stalled", status["message"].lower())
        self.assertIn("Download stalled", log.read_text(encoding="utf-8"))

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
        _isolate_scan_output(self)
        # /scans/new and /scans/start require a signed-in, allowlisted user —
        # force the dev-auth bypass on regardless of the real .env AUTH_ENABLED.
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = create_app({"TESTING": True}).test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}

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

    def test_start_spawns_even_when_postgres_has_reusable_run(self) -> None:
        from dbutils.run_access import ReusableRun

        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 424243
        reused = ReusableRun(
            run_id="scan-uuid", pillar="scan", visibility="public", slug="gpt2"
        )
        data = {
            "hf_repo": "gpt2",
            "run_modelscan": "on",
            "run_fickling": "on",
            "run_modelaudit": "on",
            "run_deps": "on",
            "run_secrets": "on",
        }
        with mock.patch("frontend.run_launch.try_lookup_reusable", return_value=reused), \
             mock.patch.object(scan_launch.subprocess, "Popen", return_value=fake_proc) as popen:
            r = self.client.post("/scans/start", data=data)
        self.assertEqual(r.status_code, 302)
        self.assertIn("status=running", r.headers["Location"])
        self.assertNotIn("status=reused", r.headers["Location"])
        popen.assert_called_once()

    def test_start_returns_503_on_output_dir_error(self) -> None:
        from frontend.output_dirs import OutputDirError

        data = {
            "hf_repo": "gpt2",
            "run_modelscan": "on",
            "run_fickling": "on",
            "run_modelaudit": "on",
            "run_deps": "on",
            "run_secrets": "on",
        }
        with mock.patch("frontend.run_launch.try_lookup_reusable", return_value=None), \
             mock.patch("frontend.scan_launch.validate_launch", return_value=None), \
             mock.patch(
                 "frontend.scan_launch.start_run",
                 side_effect=OutputDirError("cannot write to /tmp/x"),
             ):
            r = self.client.post("/scans/start", data=data)
        self.assertEqual(r.status_code, 503)
        self.assertIn(b"cannot write", r.data)

    def test_status_endpoint_returns_json(self) -> None:
        r = self.client.get("/scans/nonexistent-slug/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")


class PrivatePublicIsolationTest(unittest.TestCase):
    """Regression coverage for the reported bug: a private-mode scan must
    never see, warn about, or collide with the public catalog's result for
    the same model (and vice versa)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        for attr, value in (
            ("ROOT", root),
            ("SCAN_OUTPUT", root / "scanner" / "output"),
        ):
            patcher = mock.patch.object(scan_launch, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.out = root / "scanner" / "output"

    def _write_public_result(self, slug: str) -> None:
        d = self.out / slug
        d.mkdir(parents=True)
        (d / "scan_result.json").write_text("{}", encoding="utf-8")

    def test_existing_slugs_scoped_to_public_only(self) -> None:
        self._write_public_result("gpt2")
        self.assertIn("gpt2", scan_launch._existing_scan_slugs(visibility="public"))

    def test_existing_slugs_do_not_leak_into_private_scope(self) -> None:
        # This is the exact reported bug: a public gpt2 scan exists, but a
        # private-mode user who has never scanned anything should see no
        # warning that "a scan for gpt2 already exists".
        self._write_public_result("gpt2")
        leaked = scan_launch._existing_scan_slugs(visibility="private", owner_user_id="user-a")
        self.assertNotIn("gpt2", leaked)
        self.assertEqual(leaked, set())

    def test_private_result_does_not_leak_into_public_scope(self) -> None:
        private_dir = self.out / run_paths.PRIVATE_SEGMENT / "user-a" / "gpt2"
        private_dir.mkdir(parents=True)
        (private_dir / "scan_result.json").write_text("{}", encoding="utf-8")
        self.assertNotIn("gpt2", scan_launch._existing_scan_slugs(visibility="public"))
        self.assertIn(
            "gpt2",
            scan_launch._existing_scan_slugs(visibility="private", owner_user_id="user-a"),
        )

    def test_two_users_private_scans_are_independent(self) -> None:
        for uid in ("user-a", "user-b"):
            d = self.out / run_paths.PRIVATE_SEGMENT / uid / "gpt2"
            d.mkdir(parents=True)
            (d / "scan_result.json").write_text(json.dumps({"owner": uid}), encoding="utf-8")
        a_dir = scan_launch._private_scan_dir("gpt2", "user-a")
        b_dir = scan_launch._private_scan_dir("gpt2", "user-b")
        self.assertNotEqual(a_dir, b_dir)
        a_data = json.loads((a_dir / "scan_result.json").read_text())
        b_data = json.loads((b_dir / "scan_result.json").read_text())
        self.assertEqual(a_data["owner"], "user-a")
        self.assertEqual(b_data["owner"], "user-b")

    def test_finalize_private_scan_moves_staging_to_owner_dir_and_is_idempotent(self) -> None:
        staging = scan_launch._output_dir_for_slug("gpt2")
        staging.mkdir(parents=True)
        (staging / "scan_result.json").write_text("{}", encoding="utf-8")
        (staging / "scan_run.log").write_text("log", encoding="utf-8")

        private_dir = scan_launch._finalize_private_scan("gpt2", "user-a")
        self.assertTrue((private_dir / "scan_result.json").is_file())
        self.assertTrue((private_dir / "scan_run.log").is_file())
        self.assertFalse((staging / "scan_result.json").is_file())
        # Public scope must never see it after the move.
        self.assertNotIn("gpt2", scan_launch._existing_scan_slugs(visibility="public"))

        # Idempotent: calling again (e.g. a second status poll) is a no-op,
        # not an error, even though staging is now empty.
        again = scan_launch._finalize_private_scan("gpt2", "user-a")
        self.assertEqual(again, private_dir)
        self.assertTrue((private_dir / "scan_result.json").is_file())

    def test_get_status_reports_complete_from_private_location(self) -> None:
        staging = scan_launch._output_dir_for_slug("gpt2")
        staging.mkdir(parents=True)
        (staging / "scan_result.json").write_text("{}", encoding="utf-8")
        status = scan_launch.get_status("gpt2", visibility="private", owner_user_id="user-a")
        self.assertEqual(status["status"], "complete")
        # And the public read of the same slug sees nothing, since the
        # result was relocated into user-a's private location.
        self.assertEqual(scan_launch.get_status("gpt2")["status"], "not_found")


class UnreadableOutputDirTest(unittest.TestCase):
    """Regression: one root-owned sibling must not 500 /scans/new for everyone."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        for attr, value in (
            ("ROOT", root),
            ("SCAN_OUTPUT", root / "scanner" / "output"),
            ("DOCKER_COMPOSE_FILE", root / "scanner" / "docker" / "compose.yml"),
        ):
            patcher = mock.patch.object(scan_launch, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.out = root / "scanner" / "output"
        self.out.mkdir(parents=True)

    def _write_good_scan(self, slug: str) -> None:
        d = self.out / slug
        d.mkdir(parents=True)
        (d / "scan_result.json").write_text(
            json.dumps({"model_id": slug.replace("--", "/"), "overall_risk_score": 1}),
            encoding="utf-8",
        )

    def test_existing_slugs_skips_unreadable_sibling(self) -> None:
        self._write_good_scan("microsoft--phi-2")
        bad = self.out / "TinyLlama--TinyLlama-1.1B-Chat-v1.0"
        bad.mkdir()
        try:
            os.chmod(bad, 0)
            slugs = scan_launch._existing_scan_slugs(visibility="public")
        finally:
            os.chmod(bad, 0o755)
        self.assertIn("microsoft--phi-2", slugs)
        self.assertNotIn("TinyLlama--TinyLlama-1.1B-Chat-v1.0", slugs)

    def test_inflight_slugs_skips_unreadable_sibling(self) -> None:
        self._write_good_scan("microsoft--phi-2")
        bad = self.out / "TinyLlama--TinyLlama-1.1B-Chat-v1.0"
        bad.mkdir()
        try:
            os.chmod(bad, 0)
            slugs = scan_launch.inflight_scan_slugs()
        finally:
            os.chmod(bad, 0o755)
        self.assertIsInstance(slugs, set)

    def test_scan_run_new_returns_200_with_unreadable_sibling(self) -> None:
        from frontend import create_app

        self._write_good_scan("microsoft--phi-2")
        bad = self.out / "TinyLlama--TinyLlama-1.1B-Chat-v1.0"
        bad.mkdir()
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        client = create_app({"TESTING": True}).test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}
        try:
            os.chmod(bad, 0)
            with mock.patch("frontend.scan_data.get_scan_rerun_params", return_value={"hf_repo": "microsoft/phi-2"}):
                r = client.get("/scans/new?from=microsoft--phi-2")
        finally:
            os.chmod(bad, 0o755)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"microsoft/phi-2", r.data)


class PrivateRouteTest(unittest.TestCase):
    """A private-mode launch must redirect to the /private URL, never the
    public one — the second half of the reported bug."""

    def setUp(self) -> None:
        _isolate_scan_output(self)
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = create_app({"TESTING": True}).test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}
            sess["view_mode"] = "private"

    def test_private_launch_redirects_to_private_url(self) -> None:
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
             mock.patch.object(scan_launch.subprocess, "Popen", return_value=fake_proc):
            r = self.client.post("/scans/start", data=data)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/scans/gpt2/private", r.headers["Location"])
        self.assertNotIn("/scans/gpt2?", r.headers["Location"])

    def test_private_detail_requires_login(self) -> None:
        with self.client.session_transaction() as sess:
            sess.pop("user", None)
        r = self.client.get("/scans/gpt2/private")
        self.assertIn(r.status_code, (302, 401, 403))

    def test_delete_requires_login(self) -> None:
        # Part B: deleting a result (public or private) always requires
        # sign-in, regardless of view mode.
        with self.client.session_transaction() as sess:
            sess.pop("user", None)
        r = self.client.get("/scans/gpt2/delete")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/login", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
