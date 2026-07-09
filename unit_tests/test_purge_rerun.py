"""
Tests for rerun purge helpers — prior disk + Postgres rows removed before launch.

  uv run python -m unittest unit_tests.test_purge_rerun -v
"""

from __future__ import annotations

import unittest
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
    def test_validate_launch_purges_prior_safety(self) -> None:
        from frontend import safety_launch

        with (
            mock.patch(
                "frontend.safety_launch._eligible_gateway_models",
                return_value={"GPT 4.1 Mini"},
            ),
            mock.patch(
                "frontend.purge_rerun.purge_safety_for_launch",
                return_value=None,
            ) as purge,
            mock.patch(
                "frontend.safety_launch._prepare_output_dirs",
                return_value=None,
            ),
            mock.patch(
                "frontend.read_context.read_context",
                return_value=("public", None),
            ),
        ):
            self.assertIsNone(
                safety_launch.validate_launch("GPT 4.1 Mini", redteam_profile="base")
            )
        purge.assert_called_once()
        args, kwargs = purge.call_args
        self.assertEqual(kwargs["visibility"], "public")
        self.assertIsNone(kwargs["owner_user_id"])


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
        ):
            popen.return_value = mock.Mock()
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

        plan = mock.Mock(visibility="public", owner_user_id=None)
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
