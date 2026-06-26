import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from dbutils.env import REPO_ROOT
from safety.garak import run_garak
from safety.promptfoo.build_config import merge_redteam_config, write_redteam_config


class BuildConfigTest(unittest.TestCase):
    def test_base_profile_matches_base_yaml(self) -> None:
        base_path = (
            Path(__file__).resolve().parents[1]
            / "safety" / "promptfoo" / "promptfooconfig.base.yaml"
        )
        with base_path.open(encoding="utf-8") as f:
            base_cfg = yaml.safe_load(f)
        merged = merge_redteam_config("base")
        self.assertEqual(merged["redteam"]["plugins"], base_cfg["redteam"]["plugins"])

    def test_healthcare_profile_adds_plugins(self) -> None:
        base = merge_redteam_config("base")
        healthcare = merge_redteam_config("healthcare")
        self.assertGreater(
            len(healthcare["redteam"]["plugins"]),
            len(base["redteam"]["plugins"]),
        )

    def test_write_redteam_config_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_redteam_config("base", Path(tmp))
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "redteam_promptfooconfig.yaml")


class GarakExecutionTest(unittest.TestCase):
    def test_garak_argv_uses_repo_relative_report_dir(self) -> None:
        slug = "gpt-4.1-mini"
        garak_argv = [
            "safety/garak/run_garak.py", "GPT 4.1 Mini",
            "--report-dir", str(REPO_ROOT / "safety" / "garak" / "output" / slug),
        ]
        self.assertIn("run_garak.py", garak_argv[0])

    def test_run_garak_passes_absolute_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config_file = tmp_path / "garak_duke.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "_generator_profiles": {
                            "standard": {"type": "openai"},
                            "openai5": {"type": "openai"},
                        },
                        "plugins": {"generators": {"openai": {}}},
                    }
                ),
                encoding="utf-8",
            )
            captured: dict[str, list[str]] = {}

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                return mock.Mock(returncode=0)

            with mock.patch.object(run_garak, "CONFIG_FILE", config_file), \
                 mock.patch.object(run_garak, "_prefetch_hf_models", lambda: None), \
                 mock.patch.object(run_garak.subprocess, "run", side_effect=fake_run), \
                 mock.patch("sys.argv", ["run_garak.py", "GPT 4.1 Mini"]):
                exit_code = run_garak.main()

            self.assertEqual(exit_code, 0)
            config_arg = captured["cmd"][captured["cmd"].index("--config") + 1]
            self.assertTrue(Path(config_arg).is_absolute())


if __name__ == "__main__":
    unittest.main()
