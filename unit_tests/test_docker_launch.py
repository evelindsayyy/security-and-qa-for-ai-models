import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from dbutils.env import REPO_ROOT
from frontend import docker_launch
from safety.garak import run_garak
from safety.promptfoo.build_config import merge_redteam_config, write_redteam_config
from safety.run import RunConfig


class ComposeRunArgvTest(unittest.TestCase):
    def test_includes_docker_gid(self) -> None:
        with mock.patch.object(docker_launch, "_docker_sock_gid", return_value=998):
            argv = docker_launch.compose_run_argv("safety", ["bash", "-lc", "true"])
        self.assertIn("--project-name", argv)
        self.assertIn("qa-ai-models", argv)
        self.assertIn("DOCKER_GID=998", argv)

    def test_includes_host_repo(self) -> None:
        with mock.patch.object(docker_launch, "_docker_sock_gid", return_value=998):
            argv = docker_launch.compose_run_argv("safety", ["true"])
        self.assertIn(f"HOST_REPO={docker_launch.ROOT}", argv)


class DockerLaunchStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        docker_launch._status_cache = None

    def test_missing_cli(self) -> None:
        with mock.patch.object(docker_launch.shutil, "which", return_value=None):
            status = docker_launch.docker_launch_status(use_cache=False)
        self.assertFalse(status["available"])
        self.assertIn("docker CLI not in PATH", status["reason"])

    def test_missing_socket(self) -> None:
        mock_sock = mock.Mock()
        mock_sock.exists.return_value = False
        with mock.patch.object(docker_launch.shutil, "which", return_value="/usr/bin/docker"), \
             mock.patch.object(docker_launch, "DOCKER_SOCK", mock_sock):
            status = docker_launch.docker_launch_status(use_cache=False)
        self.assertFalse(status["available"])
        self.assertIn("socket not mounted", status["reason"])

    def test_ok(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "info"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if cmd[:3] == ["docker", "compose", "version"]:
                return subprocess.CompletedProcess(cmd, 0, "", "")
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_sock = mock.Mock()
        mock_sock.exists.return_value = True
        with mock.patch.object(docker_launch.shutil, "which", return_value="/usr/bin/docker"), \
             mock.patch.object(docker_launch, "DOCKER_SOCK", mock_sock), \
             mock.patch.object(docker_launch.subprocess, "run", side_effect=fake_run):
            status = docker_launch.docker_launch_status(use_cache=False)
        self.assertTrue(status["available"])
        self.assertEqual(status["reason"], "ok")

    def test_permission_denied(self) -> None:
        def fake_run(cmd, **kwargs):
            if cmd[:2] == ["docker", "info"]:
                raise subprocess.CalledProcessError(1, cmd, "", "permission denied")
            raise AssertionError(f"unexpected cmd: {cmd}")

        mock_sock = mock.Mock()
        mock_sock.exists.return_value = True
        with mock.patch.object(docker_launch.shutil, "which", return_value="/usr/bin/docker"), \
             mock.patch.object(docker_launch, "DOCKER_SOCK", mock_sock), \
             mock.patch.object(docker_launch.subprocess, "run", side_effect=fake_run):
            status = docker_launch.docker_launch_status(use_cache=False)
        self.assertFalse(status["available"])
        self.assertIn("DOCKER_GID", status["reason"])

    def test_docker_available_wrapper(self) -> None:
        with mock.patch.object(
            docker_launch,
            "docker_launch_status",
            return_value={"available": True, "reason": "ok"},
        ):
            self.assertTrue(docker_launch.docker_available())

    def test_docker_required_message_uses_detail(self) -> None:
        with mock.patch.object(
            docker_launch,
            "docker_detail",
            return_value="docker socket not mounted into web container",
        ):
            msg = docker_launch.docker_required_message("safety")
        self.assertIn("socket not mounted", msg)


class BuildConfigTest(unittest.TestCase):
    def test_base_profile_matches_base_yaml(self) -> None:
        base_path = (
            Path(__file__).resolve().parents[1]
            / "safety" / "promptfoo" / "promptfooconfig.base.yaml"
        )
        with base_path.open(encoding="utf-8") as f:
            base_cfg = yaml.safe_load(f)
        merged = merge_redteam_config("base")
        self.assertEqual(merged["redteam"]["plugins"], base_cfg["redteam"]["plugins"])

    def test_healthcare_profile_adds_plugins(self) -> None:
        base = merge_redteam_config("base")
        healthcare = merge_redteam_config("healthcare")
        self.assertGreater(
            len(healthcare["redteam"]["plugins"]),
            len(base["redteam"]["plugins"]),
        )

    def test_write_redteam_config_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_redteam_config("base", Path(tmp))
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "redteam_promptfooconfig.yaml")
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIn("redteam", payload)


class GarakExecutionTest(unittest.TestCase):
    def test_garak_argv_includes_run_garak_py(self) -> None:
        cfg = RunConfig(model="GPT 4.1 Mini", skip_promptfoo=True, skip_garak=False)
        slug = "gpt-4.1-mini"
        garak_argv = [
            "safety/garak/run_garak.py", cfg.model,
            "--report-dir", str(REPO_ROOT / "safety" / "garak" / "output" / slug),
        ]
        self.assertIn("run_garak.py", garak_argv[0])

    def test_run_garak_passes_absolute_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config_file = tmp_path / "garak_duke.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "_generator_profiles": {
                            "standard": {"type": "openai"},
                            "openai5": {"type": "openai"},
                        },
                        "plugins": {"generators": {"openai": {}}},
                    }
                ),
                encoding="utf-8",
            )
            captured: dict[str, list[str]] = {}

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                return mock.Mock(returncode=0)

            with mock.patch.object(run_garak, "CONFIG_FILE", config_file), \
                 mock.patch.object(run_garak, "_prefetch_hf_models", lambda: None), \
                 mock.patch.object(run_garak.subprocess, "run", side_effect=fake_run), \
                 mock.patch("sys.argv", ["run_garak.py", "GPT 4.1 Mini"]):
                exit_code = run_garak.main()

            self.assertEqual(exit_code, 0)
            config_arg = captured["cmd"][captured["cmd"].index("--config") + 1]
            self.assertTrue(Path(config_arg).is_absolute())
            self.assertTrue(config_arg.startswith(str(config_file.parent.resolve())))


if __name__ == "__main__":
    unittest.main()
