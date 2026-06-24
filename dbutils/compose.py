"""Shared Docker Compose helpers for pillar orchestrators (safety, garak setup)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from dbutils.env import REPO_ROOT, load_repo_env

ENV_FILE = REPO_ROOT / ".env"


def compose_binary() -> list[str]:
    """Return ``docker compose`` or legacy ``docker-compose`` argv prefix."""
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return ["docker", "compose"]


def compose_cmd(compose_file: Path, *, project_name: str | None = None) -> list[str]:
    """Build ``docker compose -f <file>`` argv (with optional ``--env-file .env``)."""
    load_repo_env()
    cmd = [*compose_binary()]
    if project_name:
        cmd.extend(["--project-name", project_name])
    if ENV_FILE.is_file():
        cmd.extend(["--env-file", str(ENV_FILE)])
    cmd.extend(["-f", str(compose_file)])
    return cmd


def compose_run(
    compose_file: Path,
    service: str,
    inner_cmd: list[str],
    *,
    extra_env: dict[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """``docker compose run --rm`` with optional ``-e`` overrides."""
    argv = compose_cmd(compose_file)
    argv.extend(["run", "--rm"])
    for key, val in (extra_env or {}).items():
        argv.extend(["-e", f"{key}={val}"])
    argv.extend([service, *inner_cmd])
    return subprocess.run(
        argv,
        cwd=str(cwd or REPO_ROOT),
        check=check,
        text=True,
    )


def compose_build(
    compose_file: Path,
    service: str,
    *,
    cwd: Path | None = None,
) -> None:
    """Build one compose service."""
    argv = compose_cmd(compose_file) + ["build", service]
    subprocess.run(argv, cwd=str(cwd or REPO_ROOT), check=True)
