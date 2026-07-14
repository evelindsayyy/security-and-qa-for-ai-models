"""
Default entry: containerized UI (same as ./docker/run.sh).

    uv run python main.py                  # foreground: up --build
    uv run python main.py up -d --build    # pass through any docker compose args
    uv run python main.py down
    uv run python main.py restart-deploy   # production VM: WEB_IMAGE must be set
    uv run python main.py --host           # dev Flask (PORT or APP_PORT, default 5000)

Host Flask dev needs the Vite asset watcher in a second terminal:
``cd frontend/assets && npm run dev`` (or ``npm run build`` once). Production
images build ``frontend/static/dist/`` during the Docker multi-stage build.

See docs/cli.md and auth/README.md.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RUN_SH = REPO_ROOT / "docker" / "run.sh"


def _usage() -> None:
    print(__doc__.strip(), file=sys.stderr)


def _run_host_flask() -> int:
    import socket

    from dbutils.env import load_repo_env

    load_repo_env()
    port = int(os.environ.get("PORT", os.environ.get("APP_PORT", "5000")))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as exc:
            print(
                f"Port {port} is already in use — stop the containerized UI first "
                f"(./docker/run.sh down) or choose another port: "
                f"APP_PORT=5001 uv run python main.py --host",
                file=sys.stderr,
            )
            print(f"Bind error: {exc}", file=sys.stderr)
            return 1
    from frontend import create_app

    create_app().run(debug=True, host="0.0.0.0", port=port)
    return 0


def _run_containerized(argv: list[str]) -> int:
    if not (REPO_ROOT / ".env").is_file():
        print("Missing .env — cp .env.example .env first", file=sys.stderr)
        return 1
    if not RUN_SH.is_file():
        print(f"Missing launcher: {RUN_SH}", file=sys.stderr)
        return 1
    if shutil.which("docker") is None:
        print(
            "Docker not found on PATH — install Docker or use: uv run python main.py --host",
            file=sys.stderr,
        )
        return 1

    compose_args = argv if argv else ["up", "--build"]
    return subprocess.call(["bash", str(RUN_SH), *compose_args])


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if args in (["-h"], ["--help"]):
        _usage()
        return 0

    if "--host" in args:
        rest = [a for a in args if a != "--host"]
        if rest:
            print("Unexpected args with --host:", " ".join(rest), file=sys.stderr)
            _usage()
            return 2
        return _run_host_flask()

    return _run_containerized(args)


if __name__ == "__main__":
    raise SystemExit(main())
