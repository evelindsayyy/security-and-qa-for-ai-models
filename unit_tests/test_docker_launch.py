from frontend import docker_launch


def test_compose_run_argv_includes_docker_gid(monkeypatch) -> None:
    monkeypatch.setattr(docker_launch, "_docker_sock_gid", lambda: 998)

    argv = docker_launch.compose_run_argv("safety", ["bash", "-lc", "true"])

    assert "-e" in argv
    assert "DOCKER_GID=998" in argv
