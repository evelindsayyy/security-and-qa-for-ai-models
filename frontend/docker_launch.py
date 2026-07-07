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

import logging
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

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
        os.environ.get("SCAN_LAUNCH_MODE"),
    )
    if mode is not None:
        return mode.strip().lower() != "host"
    # No explicit override. Docker bind-mount UID/GID mapping needs POSIX, so
    # default to host mode on platforms without os.getuid (e.g. Windows) where
    # the Docker launch path can't run anyway.
    return hasattr(os, "getuid")


def _docker_socket_ping(*, timeout: float = 5.0) -> bool:
    """Lightweight daemon check via the mounted socket (no CLI subprocess)."""
    sock_path = "/var/run/docker.sock"
    if not os.path.exists(sock_path):
        return False
    if not os.access(sock_path, os.R_OK | os.W_OK):
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(sock_path)
            sock.sendall(
                b"GET /_ping HTTP/1.1\r\nHost: docker\r\nConnection: close\r\n\r\n"
            )
            reply = sock.recv(256)
        return b"200" in reply or b"OK" in reply
    except OSError:
        return False


def _docker_compose_ready(*, timeout: float = 20.0) -> bool:
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=True,
            timeout=timeout,
        )
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None) or getattr(exc, "stdout", None) or str(exc)
        log.warning("docker compose version failed: %s", detail.strip() if detail else exc)
        return False


def docker_available(*, retries: int = 3) -> bool:
    """True when the host daemon and compose plugin are reachable.

    Retries absorb transient slowness when long pillar jobs are running.
    """
    for attempt in range(max(1, retries)):
        if _docker_socket_ping() and _docker_compose_ready():
            return True
        if attempt + 1 < retries:
            time.sleep(0.75 * (attempt + 1))
    log.warning("docker unavailable after %s attempt(s)", retries)
    return False


def warm_stacks_async() -> None:
    """Pre-build pillar images in the background so Start clicks do not block."""
    if not use_docker():
        return

    def _warm() -> None:
        if not docker_available(retries=2):
            log.warning("docker warm skipped — daemon not reachable at startup")
            return
        for stack in STACKS:
            try:
                ensure_stack(stack)
            except Exception:
                log.exception("docker warm failed for stack %r", stack)

    threading.Thread(target=_warm, daemon=True, name="docker-warm").start()


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
        **_passwdless_uid_env(),
        "HOST_REPO": str(ROOT),
        **(extra_env or {}),
    }.items():
        argv.extend(["-e", f"{key}={val}"])
    argv.extend([service, *inner_cmd])
    return argv


def _passwdless_uid_env() -> dict[str, str]:
    """Every pillar container runs as ``${UID}:${GID}`` (see each
    ``docker/compose.yml``) — the host user's arbitrary numeric UID, which
    has no ``/etc/passwd`` entry inside the container. Anything that calls
    ``getpass.getuser()`` (torch/transformers/bert_score do, at import
    time — hit this for real running the consistency benchmark) or writes
    to ``$HOME`` (matplotlib's config dir) then crashes or warns.
    ``USER``/``LOGNAME`` short-circuit ``getpass.getuser()`` before it ever
    falls back to the passwd lookup; ``HOME``/``MPLCONFIGDIR`` point at the
    always-writable, always-present ``/tmp`` inside the (``--rm``,
    ephemeral) container instead of the unmapped-uid's nonexistent home.
    Mirrors ``safety.run.garak_xdg_env``'s fix for the same root cause in
    garak's nested container — this is the equivalent for the four outer
    pillar containers ``compose_run_argv`` launches directly.
    """
    return {
        "USER": "runner",
        "LOGNAME": "runner",
        "HOME": "/tmp",
        "MPLCONFIGDIR": "/tmp/mplconfig",
    }


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
    if not hasattr(os, "getuid"):
        return {}
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
