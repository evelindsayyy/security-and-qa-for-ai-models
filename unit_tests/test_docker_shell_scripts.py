"""Shell script smoke tests (bash -n and no readonly UID export)."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class DockerShellScriptsTest(unittest.TestCase):
    def test_build_pillars_does_not_export_readonly_uid(self) -> None:
        text = (REPO / "docker/build-pillars.sh").read_text()
        self.assertNotIn("export UID", text)

    def test_host_env_sh_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(REPO / "docker/host-env.sh")], check=True)

    def test_build_pillars_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(REPO / "docker/build-pillars.sh")], check=True)


if __name__ == "__main__":
    unittest.main()
