import unittest
from unittest import mock

from frontend import docker_launch


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


if __name__ == "__main__":
    unittest.main()
