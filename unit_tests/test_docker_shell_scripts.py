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

    def test_deploy_remote_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(REPO / "docker/deploy-remote.sh")], check=True)

    def test_deploy_remote_accepts_provider_neutral_credentials(self) -> None:
        text = (REPO / "docker/deploy-remote.sh").read_text()
        self.assertIn("DEPLOY_GIT_URL", text)
        self.assertIn("DEPLOY_REGISTRY", text)
        self.assertIn("DEPLOY_REGISTRY_USER", text)
        self.assertIn("DEPLOY_REGISTRY_TOKEN", text)


class GitHubActionsWorkflowTest(unittest.TestCase):
    def test_workflow_runs_the_project_quality_gates(self) -> None:
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("uv run ruff check .", text)
        self.assertIn("uv run python -m unittest discover -s unit_tests -q", text)
        self.assertIn("npm run build", text)
        self.assertIn("npm run test", text)

    def test_workflow_publishes_to_ghcr_and_supports_manual_deploy(self) -> None:
        text = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("registry: ghcr.io", text)
        self.assertIn("github.event_name == 'workflow_dispatch'", text)
        self.assertIn("environment: production", text)
        self.assertIn("docker/deploy-remote.sh", text)


if __name__ == "__main__":
    unittest.main()
