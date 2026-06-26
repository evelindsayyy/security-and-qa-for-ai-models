"""Unit tests for safety.run pipeline helpers."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from safety.run import RunConfig, garak_xdg_env, parse_args, run_pipeline


class ParseArgsTest(unittest.TestCase):
    def test_default_model_from_env(self) -> None:
        with mock.patch.dict(os.environ, {"GATEWAY_MODEL": "gpt-5-chat"}):
            sub, cfg = parse_args([])
        self.assertIsNone(sub)
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.model, "gpt-5-chat")

    def test_garak_setup_subcommand(self) -> None:
        sub, cfg = parse_args(["garak-setup"])
        self.assertEqual(sub, "garak-setup")
        self.assertIsNone(cfg)

    def test_skip_flags(self) -> None:
        sub, cfg = parse_args(["--skip-garak", "--skip-redteam", "GPT 4.1 Mini"])
        self.assertIsNone(sub)
        self.assertTrue(cfg.skip_garak)
        self.assertFalse(cfg.redteam)


class GarakXdgEnvTest(unittest.TestCase):
    def test_creates_dirs_and_returns_env(self) -> None:
        env = garak_xdg_env("test-slug-xdg")
        self.assertIn("HOME", env)
        self.assertIn("test-slug-xdg", env["HOME"])
        self.assertTrue(os.path.isdir(env["HOME"]))


class RunPipelineValidationTest(unittest.TestCase):
    def test_rejects_both_skips(self) -> None:
        cfg = RunConfig(model="m", skip_promptfoo=True, skip_garak=True)
        self.assertEqual(run_pipeline(cfg), 1)

    def test_blocks_when_lock_held(self) -> None:
        from unittest import mock

        cfg = RunConfig(model="GPT 4.1 Mini", redteam_profile="base", skip_garak=True, redteam=False)
        with mock.patch("safety.run.run_lock.should_skip_cli_acquire", return_value=False):
            with mock.patch("safety.run.run_lock.try_acquire", return_value=False):
                self.assertEqual(run_pipeline(cfg), 2)


if __name__ == "__main__":
    unittest.main()
