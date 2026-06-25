"""
Shared Docker Compose helpers for browser-launched runs (scan, safety, eval, benchmarks).

All stacks read secrets from the **repo-root ``.env``** (one file, see ``.env.example``).
Compose ``environment:`` blocks map that single ``DUKE_GATEWAY_KEY`` / ``OPENAI_API_KEY``
onto whatever names each tool expects, so there are no per-stack ``.env`` files.

On first launch per stack the module:
  1. Exports the current ``UID``/``GID`` so Compose writes editable output files
  2. Runs ``docker compose build`` once (cached in-process for the Flask lifetime)

One-time pillar image builds: ``./docker/build-pillars.sh`` (see root README).

Set ``FRONTEND_LAUNCH_MODE=host`` to force the legacy host-Python path (unit tests,
local debugging). CLI READMEs still document the manual docker compose workflow.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
COMPOSE_PROJECT_NAME = os.environ.get("COMPOSE_PROJECT_NAME", "qa-ai-models")

# stack_key -> (compose_file relative to ROOT, service name)
STACKS: dict[str, tuple[Path, str]] = {
    "scanner": (Path("scanner/docker/compose.yml"), "scanner"),
    "evaluator": (Path("evaluator/docker/compose.yml"), "evaluator"),
    "benchmarks": (Path("benchmarks/docker/compose.yml"), "benchmarks"),
    "safety": (Path("safety/docker/compose.yml"), "safety"),
}

_ready: set[str] = set()
_lock = threading.Lock()


def use_docker() -> bool:
    mode = os.environ.get(
        "FRONTEND_LAUNCH_MODE",
        os.environ.get("SCAN_LAUNCH_MODE", "docker"),
    )
    return mode.strip().lower() != "host"


def docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=True,
            timeout=15,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def docker_required_message(stack: str) -> str:
    compose, _ = _stack_paths(stack)
    return (
        f"Docker is required for browser-launched {stack} runs — install Docker and ensure "
        f"`{compose.relative_to(ROOT)}` is built, or set FRONTEND_LAUNCH_MODE=host "
        f"(CLI-only fallback)."
    )


def compose_run_argv(
    stack: str,
    inner_cmd: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> list[str]:
    """Build ``docker compose --env-file .env run --rm -T <service> …`` argv for *stack*."""
    compose, service = _stack_paths(stack)
    argv = ["docker", "compose", "--project-name", COMPOSE_PROJECT_NAME]
    if ENV_FILE.is_file():
        argv += ["--env-file", str(ENV_FILE)]
    argv += ["-f", str(compose), "run", "--rm", "-T"]
    # UID/GID inside the container so nested compose (safety) and bind-mounted
    # output files use the host user, not root.
    # Also pass the host docker.sock group id so the safety container can access
    # the daemon via the mounted socket.
    for key, val in {
        **_uid_gid_env(),
        **_docker_gid_env(),
        "HOST_REPO": str(ROOT),
        **(extra_env or {}),
    }.items():
        argv.extend(["-e", f"{key}={val}"])
    argv.extend([service, *inner_cmd])
    return argv


def ensure_stack(stack: str) -> None:
    """One-time ``docker compose build`` for a pillar stack (UID/GID exported first)."""
    if not use_docker():
        return
    with _lock:
        if stack in _ready:
            return
        _export_uid_gid()
        compose, service = _stack_paths(stack)
        _compose_build(compose, service)
        _ready.add(stack)


def _stack_paths(stack: str) -> tuple[Path, str]:
    if stack not in STACKS:
        raise KeyError(f"unknown docker stack: {stack!r}")
    compose_rel, service = STACKS[stack]
    compose = ROOT / compose_rel
    if not compose.is_file():
        raise FileNotFoundError(f"missing compose file: {compose}")
    return compose, service


def _uid_gid_env() -> dict[str, str]:
    return {"UID": str(os.getuid()), "GID": str(os.getgid())}


def _docker_sock_gid() -> int | None:
    try:
        return os.stat("/var/run/docker.sock").st_gid
    except FileNotFoundError:
        return None


def _docker_gid_env() -> dict[str, str]:
    gid = _docker_sock_gid()
    return {"DOCKER_GID": str(gid)} if gid is not None else {}


def _export_uid_gid() -> None:
    """Put UID/GID, Docker socket GID, and compose project name in the process env."""
    env = {
        **_uid_gid_env(),
        **_docker_gid_env(),
        "COMPOSE_PROJECT_NAME": COMPOSE_PROJECT_NAME,
    }
    os.environ.update(env)


def _compose_cmd(compose: Path) -> list[str]:
    cmd = ["docker", "compose", "--project-name", COMPOSE_PROJECT_NAME]
    if ENV_FILE.is_file():
        cmd += ["--env-file", str(ENV_FILE)]
    return cmd + ["-f", str(compose)]


def _compose_image_ready(compose: Path, service: str) -> bool:
    cmd = _compose_cmd(compose) + ["images", "-q", service]
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return bool(result.stdout.strip())


def _compose_build(compose: Path, service: str) -> None:
    if _compose_image_ready(compose, service):
        return
    cmd = _compose_cmd(compose) + ["build", service]
    try:
        subprocess.run(cmd, cwd=str(ROOT), check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        if _compose_image_ready(compose, service):
            return
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(
            f"docker compose build failed for {service!r} — {detail}"
        ) from exc
