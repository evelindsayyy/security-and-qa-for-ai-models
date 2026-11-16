"""
`python main.py --host`: the port pre-check and Werkzeug's debug reloader.

With debug=True, Werkzeug's parent process binds the port, then re-runs
main.py in a child (WERKZEUG_RUN_MAIN=true) that serves on the inherited
socket. The pre-check must not run in that child: the port is busy because the
parent holds it, and refusing there stopped the dev server on every start.

Run from repo root:
  uv run python -m unittest unit_tests.test_main_host -v
"""

from __future__ import annotations

import importlib.util
import os
import socket
import unittest
from pathlib import Path
from unittest import mock

# Loaded by path: other tests put directories with their own `main` module
# (frontend/, docs/...) on sys.path, so `import main` depends on test order.
_SPEC = importlib.util.spec_from_file_location("repo_main", Path(__file__).resolve().parent.parent / "main.py")
main = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(main)


def _busy_port() -> tuple[socket.socket, int]:
    """A listening socket on a free port, standing in for whoever holds it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("0.0.0.0", 0))
    sock.listen()
    return sock, sock.getsockname()[1]


class FakeApp:
    def __init__(self) -> None:
        self.ran_with: dict | None = None

    def run(self, **kwargs) -> None:
        self.ran_with = kwargs


class HostFlaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.holder, self.port = _busy_port()
        self.addCleanup(self.holder.close)
        self.app = FakeApp()
        for target, value in (
            ("dbutils.env.load_repo_env", lambda: None),
            ("frontend.create_app", lambda: self.app),
        ):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_host(self, reloader_child: bool) -> int:
        with mock.patch.dict(os.environ, {"APP_PORT": str(self.port)}):
            os.environ.pop("PORT", None)  # read before APP_PORT
            if reloader_child:
                os.environ["WERKZEUG_RUN_MAIN"] = "true"
            else:
                os.environ.pop("WERKZEUG_RUN_MAIN", None)
            return main._run_host_flask()

    def test_a_port_held_by_another_process_is_refused(self) -> None:
        self.assertEqual(self.run_host(reloader_child=False), 1)
        self.assertIsNone(self.app.ran_with)

    def test_the_reloader_child_serves_on_its_parents_port(self) -> None:
        self.assertEqual(self.run_host(reloader_child=True), 0)
        self.assertEqual(self.app.ran_with["port"], self.port)


if __name__ == "__main__":
    unittest.main()
