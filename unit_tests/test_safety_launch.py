"""
Tests for safety browser launch — no subprocess spawn, no gateway calls.

  uv run python -m unittest unit_tests.test_safety_launch -v
"""

from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import safety_launch  # noqa: E402


def _isolate_safety_output(test_case: unittest.TestCase) -> Path:
    """Redirect safety_launch's ROOT-derived output paths to a scratch
    tempdir and reset its in-memory run registries — see
    test_scan_launch._isolate_scan_output for why this matters (a mocked
    launch still writes real state under safety/output/<slug>/... and
    safety_launch._RUNNING/_INFLIGHT otherwise, which a background thread
    cleans up on an unsynchronized timer, racing later tests in this file
    that check "is <slug> already running")."""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    patcher = mock.patch.object(safety_launch, "ROOT", root)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    test_case.addCleanup(safety_launch._RUNNING.clear)
    test_case.addCleanup(safety_launch._INFLIGHT.clear)
    return root


class ValidateLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(
            safety_launch,
            "_eligible_gateway_models",
            return_value=safety_launch._GATEWAY_FALLBACK,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_model_passes(self) -> None:
        self.assertIsNone(safety_launch.validate_launch("gpt-5.5"))

    def test_unknown_model_rejected(self) -> None:
        err = safety_launch.validate_launch("rm -rf /")
        self.assertIn("not eligible", err)

    def test_skip_both_promptfoo_and_garak_rejected(self) -> None:
        err = safety_launch.validate_launch(
            "gpt-5.5", skip_promptfoo=True, skip_garak=True
        )
        self.assertIn("cannot skip both", err)

    def test_invalid_garak_probes_rejected(self) -> None:
        err = safety_launch.validate_launch(
            "gpt-5.5", garak_probes="dan; rm -rf /"
        )
        self.assertIn("garak_probes", err)

    def test_valid_garak_probes_pass(self) -> None:
        self.assertIsNone(
            safety_launch.validate_launch(
                "gpt-5.5",
                garak_probes="latentinjection.LatentInjectionFactSnippetEiffel",
            )
        )


class BuildCommandTest(unittest.TestCase):
    def test_command_is_argv_list(self) -> None:
        cmd = safety_launch.build_command("gpt-5.5")
        self.assertIsInstance(cmd, list)
        self.assertIn("safety.run", " ".join(cmd))
        self.assertIn("gpt-5.5", cmd)

    def test_garak_probes_forwarded(self) -> None:
        cmd = safety_launch.build_command(
            "gpt-5.5",
            garak_probes="encoding,dan.Dan_11_0",
        )
        self.assertIn("--garak-probes", cmd)
        idx = cmd.index("--garak-probes")
        self.assertEqual(cmd[idx + 1], "encoding,dan.Dan_11_0")


class GetStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        patcher = mock.patch.object(safety_launch, "ROOT", root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = root / "safety" / "output"

    def test_unsafe_slug_is_not_found(self) -> None:
        self.assertEqual(safety_launch.get_status("../../etc", "base")["status"], "not_found")

    def test_complete_when_merged_exists(self) -> None:
        slug = "gpt-5.5"
        (self.out / slug / "base").mkdir(parents=True)
        (self.out / slug / "base" / "merged_safety_result.json").write_text("{}", encoding="utf-8")
        self.assertEqual(safety_launch.get_status(slug, "base")["status"], "complete")

    def test_partial_when_missing_suites(self) -> None:
        slug = "gpt-5.5"
        (self.out / slug / "base").mkdir(parents=True)
        merged = self.out / slug / "base" / "merged_safety_result.json"
        merged.write_text(
            '{"missing_suites": ["garak_subset_v1"]}',
            encoding="utf-8",
        )
        status = safety_launch.get_status(slug, "base")
        self.assertEqual(status["status"], "partial")
        self.assertIn("Garak", status["warnings"])

    def test_running_alert_when_garak_failed_in_log(self) -> None:
        slug = "gpt-5.5"
        profile = "base"
        (self.out / slug / profile).mkdir(parents=True)
        log_path = self.out / slug / profile / "run.log"
        log_path.write_text(
            "ERROR: Garak finished (exit 0) but no report in safety/garak/output\n",
            encoding="utf-8",
        )
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        safety_launch._RUNNING[f"{slug}/{profile}"] = fake_proc
        self.addCleanup(lambda: safety_launch._RUNNING.pop(f"{slug}/{profile}", None))
        status = safety_launch.get_status(slug, profile)
        self.assertEqual(status["status"], "running")
        self.assertIn("alert", status)
        self.assertIn("Garak failed", status["alert"])

    def test_complete_when_merged_exists_despite_failed_proc(self) -> None:
        slug = "gpt-4.1-mini"
        (self.out / slug / "base").mkdir(parents=True)
        (self.out / slug / "base" / "merged_safety_result.json").write_text("{}", encoding="utf-8")
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = 1
        fake_proc.returncode = 1
        safety_launch._RUNNING[f"{slug}/base"] = fake_proc
        self.addCleanup(lambda: safety_launch._RUNNING.pop(f"{slug}/base", None))
        self.assertEqual(safety_launch.get_status(slug, "base")["status"], "complete")

    def test_stale_lock_with_complete_log_returns_failed(self) -> None:
        slug = "llama-3.3"
        profile = "base"
        run_dir = self.out / slug / profile
        run_dir.mkdir(parents=True)
        log_path = run_dir / "run.log"
        log_path.write_text("--- Merge ---\nComplete: safety/output/llama-3.3/base/merged.json\n")
        lock_path = run_dir / "run.lock"
        lock_path.write_text(
            '{"pid": 1, "source": "cli", "started_at": "2025-06-29T00:00:00Z"}',
            encoding="utf-8",
        )
        status = safety_launch.get_status(slug, profile)
        self.assertEqual(status["status"], "failed")
        self.assertFalse(lock_path.is_file())

    def test_partial_when_garak_incomplete_in_merged(self) -> None:
        slug = "gpt-4.1-mini"
        (self.out / slug / "base").mkdir(parents=True)
        merged = self.out / slug / "base" / "merged_safety_result.json"
        merged.write_text(
            json.dumps(
                {
                    "missing_suites": [],
                    "tool_results": {
                        "garak_subset_v1": {
                            "garak": {
                                "expected_modules": 13,
                                "completed_modules": 6,
                                "report_complete": False,
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        status = safety_launch.get_status(slug, "base")
        self.assertEqual(status["status"], "partial")
        self.assertTrue(any("partial" in w.lower() for w in status["warnings"]))


class LaunchRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        _isolate_safety_output(self)
        safety_launch._RUNNING.clear()
        safety_launch._INFLIGHT.clear()
        patcher = mock.patch.object(
            safety_launch,
            "_eligible_gateway_models",
            return_value=safety_launch._GATEWAY_FALLBACK,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        # /safety/new and /safety/start require a signed-in, allowlisted user —
        # force the dev-auth bypass on regardless of the real .env AUTH_ENABLED.
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = create_app({"TESTING": True}).test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}

    def test_form_renders(self) -> None:
        r = self.client.get("/safety/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gpt-5.5", r.data)

    def test_start_rejects_ineligible_model(self) -> None:
        r = self.client.post("/safety/start", data={"gateway_model": "evil-model"})
        self.assertEqual(r.status_code, 400)

    def test_start_valid_spawns_and_redirects(self) -> None:
        from frontend.run_launch import LaunchPlan

        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        fake_proc.pid = 424242
        fresh_plan = LaunchPlan(
            config={"gateway_model": "gpt-5.5"},
            config_fingerprint="test-fp",
            visibility="public",
            owner_user_id=None,
            owner_netid=None,
            reused=None,
        )
        with mock.patch.object(
            safety_launch.subprocess, "Popen", return_value=fake_proc
        ) as popen, mock.patch(
            "frontend.run_launch.build_launch_plan", return_value=fresh_plan
        ), mock.patch.object(safety_launch, "is_safety_inflight", return_value=False), mock.patch.object(
            safety_launch, "check_inflight_combo", return_value=None
        ), mock.patch.object(safety_launch.docker_launch, "use_docker", return_value=False), mock.patch(
            "dbutils.run_lock.try_acquire", return_value=True
        ):
            r = self.client.post("/safety/start", data={
                "gateway_model": "gpt-5.5",
                "run_policy": "1",
                "run_redteam": "1",
                "run_garak": "1",
            })
        self.assertEqual(r.status_code, 302, r.data[:500] if r.data else r.status_code)
        self.assertIn("status=running", r.headers["Location"])
        popen.assert_called_once()
        self.assertIsInstance(popen.call_args.args[0], list)

    def test_status_endpoint_returns_json(self) -> None:
        r = self.client.get("/safety/nonexistent-slug/base/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")

    def test_delete_requires_login(self) -> None:
        with self.client.session_transaction() as sess:
            sess.pop("user", None)
        r = self.client.get("/safety/gpt-5.5/base/delete")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/login", r.headers["Location"])

    def test_private_detail_requires_login(self) -> None:
        with self.client.session_transaction() as sess:
            sess.pop("user", None)
        r = self.client.get("/safety/gpt-5.5/base/private")
        self.assertIn(r.status_code, (302, 401, 403))


if __name__ == "__main__":
    unittest.main()
