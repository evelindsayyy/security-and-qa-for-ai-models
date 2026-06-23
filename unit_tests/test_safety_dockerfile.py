from pathlib import Path


def test_safety_dockerfile_installs_docker_compose_fallback() -> None:
    dockerfile = Path("safety/docker/Dockerfile").read_text(encoding="utf-8")

    assert "docker-compose" in dockerfile
    # deps are installed via uv sync (not pip) since the uv migration
    assert "uv sync" in dockerfile
