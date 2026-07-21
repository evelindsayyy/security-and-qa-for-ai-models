"""
Tests for rerun purge helpers — prior disk + Postgres rows removed before launch.

  uv run python -m unittest unit_tests.test_purge_rerun -v
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock


class PurgeScanLaunchTest(unittest.TestCase):
    def test_validate_launch_purges_prior_scan(self) -> None:
        from frontend import scan_launch

        with (
            mock.patch(
                "frontend.purge_rerun.purge_scan_for_launch",
                return_value=None,
            ) as purge,
            mock.patch(
                "frontend.scan_launch.prepare_output_dir",
                return_value=None,
            ),
            mock.patch(
                "frontend.read_context.read_context",
                return_value=("public", None),
            ),
        ):
            self.assertIsNone(scan_launch.validate_launch("microsoft/phi-2"))
        purge.assert_called_once_with(
            "microsoft--phi-2", visibility="public", owner_user_id=None
        )

    def test_validate_launch_surfaces_purge_error(self) -> None:
        from frontend import scan_launch

        with (
            mock.patch(
                "frontend.purge_rerun.purge_scan_for_launch",
                return_value="database delete failed",
            ),
            mock.patch(
                "frontend.scan_launch.prepare_output_dir",
                return_value=None,
            ),
            mock.patch(
                "frontend.read_context.read_context",
                return_value=("public", None),
            ),
        ):
            err = scan_launch.validate_launch("gpt2")
        self.assertEqual(err, "database delete failed")


class PurgeSafetyLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        from frontend import safety_launch

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.object(safety_launch, "ROOT", Path(tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(safety_launch._RUNNING.clear)
        self.addCleanup(safety_launch._INFLIGHT.clear)

    def test_start_run_purges_prior_safety(self) -> None:
        """Purge (like the output-dir wipe) must happen inside start_run(),
        *after* it claims the cross-process lock — not in validate_launch(),
        which runs unlocked and would otherwise race a second concurrent
        validate+start request the same way the pre-fix start_run() used
        to (see StartRunLockOrderingTest in test_safety_launch.py)."""
        from frontend import safety_launch

        plan = mock.Mock(visibility="public", owner_user_id=None)
        fake_proc = mock.Mock(pid=4242, poll=mock.Mock(return_value=None))
        with (
            mock.patch("frontend.run_launch.build_launch_plan", return_value=plan),
            mock.patch(
                "frontend.purge_rerun.purge_safety_for_launch",
                return_value=None,
            ) as purge,
            mock.patch.object(safety_launch, "_wipe_outputs"),
            mock.patch.object(safety_launch.docker_launch, "use_docker", return_value=False),
            mock.patch.object(safety_launch.subprocess, "Popen", return_value=fake_proc),
            mock.patch.object(safety_launch, "threading"),
            mock.patch("frontend.run_launch.persist_run_meta_dir"),
        ):
            safety_launch.start_run("GPT 4.1 Mini", redteam_profile="base")
        purge.assert_called_once_with(
            "gpt-4.1-mini", "base", visibility="public", owner_user_id=None
        )

    def test_validate_launch_does_not_purge(self) -> None:
        """validate_launch() is a pure check now — no purge, no wipe (see
        the docstring above)."""
        from frontend import safety_launch

        with (
            mock.patch(
                "frontend.safety_launch._eligible_gateway_models",
                return_value={"GPT 4.1 Mini"},
            ),
            mock.patch(
                "frontend.purge_rerun.purge_safety_for_launch",
            ) as purge,
            mock.patch.object(safety_launch, "_prepare_output_dirs") as prepare,
        ):
            self.assertIsNone(
                safety_launch.validate_launch("GPT 4.1 Mini", redteam_profile="base")
            )
        purge.assert_not_called()
        prepare.assert_not_called()


class PurgeEvalLaunchTest(unittest.TestCase):
    def test_start_run_purges_prior_eval(self) -> None:
        from frontend import eval_launch

        plan = mock.Mock(visibility="public", owner_user_id=None)
        with (
            mock.patch("frontend.run_launch.build_launch_plan", return_value=plan),
            mock.patch("frontend.eval_launch.check_inflight_combo", return_value=None),
            mock.patch(
                "frontend.purge_rerun.purge_eval_for_launch",
                return_value=None,
            ) as purge,
            mock.patch("frontend.eval_launch.build_command", return_value=["echo"]),
            mock.patch("frontend.eval_launch.docker_launch.use_docker", return_value=False),
            mock.patch("frontend.eval_launch.subprocess.Popen") as popen,
            mock.patch("frontend.run_launch.persist_run_meta_dir"),
            mock.patch("frontend.eval_launch.threading.Thread"),
        ):
            popen.return_value = mock.Mock(
                pid=4242,
                poll=mock.Mock(return_value=None),
                wait=mock.Mock(),
            )
            eval_launch.start_run("GPT 4.1 Mini", "GPT 4.1", "it_support", 1024)
        purge.assert_called_once_with(
            "it_support",
            "GPT 4.1 Mini",
            visibility="public",
            owner_user_id=None,
        )


class PurgeBenchmarkLaunchTest(unittest.TestCase):
    def test_start_run_purges_prior_benchmark(self) -> None:
        from frontend import benchmark_launch

        plan = mock.Mock(
            visibility="public",
            owner_user_id=None,
            config={},
            config_fingerprint="fp",
            owner_netid=None,
            reused=None,
        )
        with (
            mock.patch("frontend.run_launch.build_launch_plan", return_value=plan),
            mock.patch("frontend.benchmark_launch.check_inflight_combo", return_value=None),
            mock.patch(
                "frontend.purge_rerun.purge_benchmark_for_launch",
                return_value=None,
            ) as purge,
            mock.patch("frontend.benchmark_launch.docker_launch.use_docker", return_value=False),
            mock.patch("frontend.benchmark_launch.subprocess.Popen") as popen,
            mock.patch("frontend.run_launch.persist_run_meta_dir"),
            mock.patch("frontend.benchmark_launch.write_progress_stub"),
            mock.patch("frontend.benchmark_launch._write_run_options"),
            mock.patch("frontend.benchmark_launch.run_lock.try_acquire", return_value=True),
        ):
            popen.return_value = mock.Mock()
            benchmark_launch.start_run("mmlu", "GPT 4.1 Mini")
        purge.assert_called_once_with(
            "mmlu",
            "GPT 4.1 Mini",
            visibility="public",
            owner_user_id=None,
        )


if __name__ == "__main__":
    unittest.main()
