import socket
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


class DockerAvailableTest(unittest.TestCase):
    def test_succeeds_when_socket_and_compose_ready(self) -> None:
        with (
            mock.patch.object(docker_launch, "_docker_socket_ping", return_value=True),
            mock.patch.object(docker_launch, "_docker_compose_ready", return_value=True),
        ):
            self.assertTrue(docker_launch.docker_available(retries=1))

    def test_retries_when_compose_flaky(self) -> None:
        with (
            mock.patch.object(docker_launch, "_docker_socket_ping", return_value=True),
            mock.patch.object(
                docker_launch,
                "_docker_compose_ready",
                side_effect=[False, True],
            ),
            mock.patch.object(docker_launch, "time") as time_mod,
        ):
            self.assertTrue(docker_launch.docker_available(retries=2))
        time_mod.sleep.assert_called_once()

    def test_fails_when_socket_unreachable(self) -> None:
        with (
            mock.patch.object(docker_launch, "_docker_socket_ping", return_value=False),
            mock.patch.object(docker_launch, "_docker_compose_ready") as compose,
            mock.patch.object(docker_launch, "time"),
        ):
            self.assertFalse(docker_launch.docker_available(retries=2))
        compose.assert_not_called()


class DockerSocketPingTest(unittest.TestCase):
    def test_ping_accepts_ok_response(self) -> None:
        fake = mock.Mock(spec=socket.socket)
        fake.recv.return_value = b"HTTP/1.1 200 OK\r\n\r\nOK"
        ctx = mock.MagicMock()
        ctx.__enter__.return_value = fake
        with (
            mock.patch.object(docker_launch.os, "path", wraps=docker_launch.os.path),
            mock.patch.object(docker_launch.os, "access", return_value=True),
            mock.patch.object(docker_launch.socket, "socket", return_value=ctx),
        ):
            self.assertTrue(docker_launch._docker_socket_ping())


if __name__ == "__main__":
    unittest.main()
