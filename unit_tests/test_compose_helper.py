"""Unit tests for dbutils.compose helpers."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from dbutils.compose import compose_binary, compose_cmd


class ComposeHelperTest(unittest.TestCase):
    def test_compose_binary_prefers_docker_compose_when_present(self) -> None:
        with mock.patch("dbutils.compose.shutil.which", return_value="/usr/bin/docker-compose"):
            self.assertEqual(compose_binary(), ["docker-compose"])

    def test_compose_binary_falls_back_to_docker_compose_plugin(self) -> None:
        with mock.patch("dbutils.compose.shutil.which", return_value=None):
            self.assertEqual(compose_binary(), ["docker", "compose"])

    def test_compose_cmd_includes_compose_file(self) -> None:
        compose_file = Path("/tmp/test-compose.yml")
        with mock.patch("dbutils.compose.shutil.which", return_value=None), \
             mock.patch("dbutils.compose.ENV_FILE") as env_file:
            env_file.is_file.return_value = False
            cmd = compose_cmd(compose_file)
        self.assertIn("-f", cmd)
        self.assertIn(str(compose_file), cmd)


if __name__ == "__main__":
    unittest.main()
