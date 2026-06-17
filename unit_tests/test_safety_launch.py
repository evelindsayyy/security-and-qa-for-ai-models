"""
Tests for safety browser launch — no subprocess spawn, no gateway calls.

  uv run python -m unittest unit_tests.test_safety_launch -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import safety_launch  # noqa: E402


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
        self.assertIn("run_safety.sh", " ".join(cmd))
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
        self.assertEqual(safety_launch.get_status("../../etc")["status"], "not_found")

    def test_complete_when_merged_exists(self) -> None:
        slug = "gpt-5.5"
        (self.out / slug).mkdir(parents=True)
        (self.out / slug / "merged_safety_result.json").write_text("{}", encoding="utf-8")
        self.assertEqual(safety_launch.get_status(slug)["status"], "complete")


class LaunchRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(
            safety_launch,
            "_eligible_gateway_models",
            return_value=safety_launch._GATEWAY_FALLBACK,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = create_app({"TESTING": True}).test_client()

    def test_form_renders(self) -> None:
        r = self.client.get("/safety/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gpt-5.5", r.data)

    def test_start_rejects_ineligible_model(self) -> None:
        r = self.client.post("/safety/start", data={"gateway_model": "evil-model"})
        self.assertEqual(r.status_code, 400)

    def test_start_valid_spawns_and_redirects(self) -> None:
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
        with mock.patch.object(
            safety_launch.subprocess, "Popen", return_value=fake_proc
        ) as popen:
            r = self.client.post("/safety/start", data={"gateway_model": "gpt-5.5"})
        self.assertEqual(r.status_code, 302)
        self.assertIn("status=running", r.headers["Location"])
        popen.assert_called_once()
        self.assertIsInstance(popen.call_args.args[0], list)

    def test_status_endpoint_returns_json(self) -> None:
        r = self.client.get("/safety/nonexistent-slug/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")


if __name__ == "__main__":
    unittest.main()
