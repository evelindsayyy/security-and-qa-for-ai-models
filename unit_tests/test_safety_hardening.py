import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from dbutils.env import REPO_ROOT
from safety.garak import run_garak
from safety.promptfoo.build_config import merge_redteam_config, write_redteam_config
from unit_tests.garak_test_helpers import install_fake_garak, remove_fake_garak

DUKE14_PROBE_SPEC = (
    "packagehallucination,snowball,encoding,goodside,web_injection,sysprompt_extraction,"
    "apikey,promptinject,dan.Dan_11_0,dan.DanInTheWild,misleading,leakreplay,latentinjection,"
    "divergence"
)


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
                        "plugins": {
                            "generators": {"openai": {}},
                            "probe_spec": DUKE14_PROBE_SPEC,
                        },
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
                 mock.patch.object(run_garak, "_prefetch_toxic_detector", lambda: None), \
                 mock.patch.object(run_garak, "_validate_probe_spec", return_value=(14, 62)), \
                 mock.patch.object(run_garak.subprocess, "run", side_effect=fake_run), \
                 mock.patch("sys.argv", ["run_garak.py", "GPT 4.1 Mini"]):
                exit_code = run_garak.main()

            self.assertEqual(exit_code, 0)
            config_arg = captured["cmd"][captured["cmd"].index("--config") + 1]
            self.assertTrue(Path(config_arg).is_absolute())
            garak_dir = REPO_ROOT / "safety" / "garak"
            self.assertNotEqual(Path(config_arg).parent.resolve(), garak_dir.resolve())
            self.assertIn("-p", captured["cmd"])
            p_idx = captured["cmd"].index("-p")
            self.assertEqual(captured["cmd"][p_idx + 1], DUKE14_PROBE_SPEC)

    def test_duke14_probe_spec_in_yaml(self) -> None:
        cfg = yaml.safe_load(run_garak.CONFIG_FILE.read_text(encoding="utf-8"))
        probe_spec = cfg["plugins"]["probe_spec"]
        self.assertEqual(probe_spec, DUKE14_PROBE_SPEC)
        self.assertEqual(len(probe_spec.split(",")), 14)
        self.assertNotIn("propile", probe_spec)

    def test_validate_probe_spec_rejects_propile(self) -> None:
        fake = install_fake_garak(rejected=["propile"], names=[])
        self.addCleanup(lambda: remove_fake_garak(fake))
        with self.assertRaises(SystemExit) as ctx:
            run_garak._validate_probe_spec("propile")
        self.assertEqual(ctx.exception.code, 1)

    def test_validate_probe_spec_accepts_duke14(self) -> None:
        fake = install_fake_garak(names=["encoding.InjectHex"] * 62)
        self.addCleanup(lambda: remove_fake_garak(fake))
        modules, sub_probes = run_garak._validate_probe_spec(DUKE14_PROBE_SPEC)
        self.assertEqual(modules, 14)
        self.assertGreater(sub_probes, 0)


if __name__ == "__main__":
    unittest.main()
