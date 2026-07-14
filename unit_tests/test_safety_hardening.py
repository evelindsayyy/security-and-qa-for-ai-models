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

    def test_education_profile_adds_plugins(self) -> None:
        # healthcare/finance/rag/agentic's plugins mostly require Promptfoo Cloud
        # and are commented out pending a shared service account (see
        # promptfoo_profiles.yaml); education is the profile with active,
        # locally-runnable additional_plugins today.
        base = merge_redteam_config("base")
        education = merge_redteam_config("education")
        self.assertGreater(
            len(education["redteam"]["plugins"]),
            len(base["redteam"]["plugins"]),
        )

    def test_write_redteam_config_creates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_redteam_config("base", Path(tmp))
            self.assertTrue(path.is_file())
            self.assertEqual(path.name, "redteam_promptfooconfig.yaml")


class PolicyConfigTest(unittest.TestCase):
    def test_api_base_url_templated_with_duke_default(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "safety" / "promptfoo" / "promptfooconfig.yaml"
        )
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        api_base_url = cfg["providers"][0]["config"]["apiBaseUrl"]
        self.assertIn("{{ env.GATEWAY_BASE_URL", api_base_url)
        self.assertIn("https://litellm.oit.duke.edu/v1", api_base_url)


class RedteamConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "safety" / "promptfoo" / "promptfooconfig.base.yaml"
        )
        self.cfg = yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_target_url_templated_with_duke_default(self) -> None:
        api_base_url = self.cfg["targets"][0]["config"]["apiBaseUrl"]
        self.assertIn("{{ env.GATEWAY_BASE_URL", api_base_url)
        self.assertIn("https://litellm.oit.duke.edu/v1", api_base_url)

    def test_attacker_model_falls_back_to_target_model(self) -> None:
        attacker_id = self.cfg["redteam"]["provider"]["id"]
        self.assertIn("env.REDTEAM_ATTACKER_MODEL", attacker_id)
        self.assertIn("default(env.GATEWAY_MODEL)", attacker_id)

    def test_attacker_url_falls_back_to_target_url_then_duke(self) -> None:
        attacker_url = self.cfg["redteam"]["provider"]["config"]["apiBaseUrl"]
        self.assertIn("env.REDTEAM_ATTACKER_BASE_URL", attacker_url)
        self.assertIn("env.GATEWAY_BASE_URL", attacker_url)
        self.assertIn("https://litellm.oit.duke.edu/v1", attacker_url)

    def test_grader_always_pinned_to_duke(self) -> None:
        # The grader must NOT follow the target/attacker fallback chain — it's
        # meant to stay a fixed, independent judge regardless of what's tested.
        grader_url = self.cfg["defaultTest"]["options"]["provider"]["config"]["apiBaseUrl"]
        self.assertEqual(grader_url, "https://litellm.oit.duke.edu/v1")
        self.assertNotIn("{{", grader_url)


class ManualEvalConfigTest(unittest.TestCase):
    """manual/*.yaml run during redteam scans too — same target-URL gap as
    promptfooconfig.base.yaml applied here independently, since each file
    has its own providers: block (found by checking after fixing the main
    redteam config and realizing these were never touched)."""

    MANUAL_YAML_FILES = ("bias.yaml", "remote_policy.yaml", "harmful_content.yaml")

    def test_target_url_templated_with_duke_default(self) -> None:
        manual_dir = (
            Path(__file__).resolve().parents[1]
            / "safety" / "promptfoo" / "manual"
        )
        for name in self.MANUAL_YAML_FILES:
            with self.subTest(file=name):
                cfg = yaml.safe_load((manual_dir / name).read_text(encoding="utf-8"))
                api_base_url = cfg["providers"][0]["config"]["apiBaseUrl"]
                self.assertIn("{{ env.GATEWAY_BASE_URL", api_base_url)
                self.assertIn("https://litellm.oit.duke.edu/v1", api_base_url)

    def test_grader_still_pinned_to_duke(self) -> None:
        manual_dir = (
            Path(__file__).resolve().parents[1]
            / "safety" / "promptfoo" / "manual"
        )
        for name in self.MANUAL_YAML_FILES:
            with self.subTest(file=name):
                cfg = yaml.safe_load((manual_dir / name).read_text(encoding="utf-8"))
                grader_url = cfg["defaultTest"]["options"]["provider"]["config"]["apiBaseUrl"]
                self.assertEqual(grader_url, "https://litellm.oit.duke.edu/v1")


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

    def test_resolve_generator_cfg_no_base_url_uses_duke_profile(self) -> None:
        cfg = {
            "_generator_profiles": {
                "standard": {"uri": "https://litellm.oit.duke.edu/v1/", "temperature": 0},
                "openai5": {"uri": "https://litellm.oit.duke.edu/v1/", "extra_params": {}},
            }
        }
        profile, generator_cfg = run_garak._resolve_generator_cfg(cfg, "GPT 4.1 Mini", None)
        self.assertEqual(profile, "standard")
        self.assertEqual(generator_cfg["uri"], "https://litellm.oit.duke.edu/v1/")

    def test_resolve_generator_cfg_base_url_overrides_duke(self) -> None:
        cfg = {
            "_generator_profiles": {
                "standard": {"uri": "https://litellm.oit.duke.edu/v1/", "temperature": 0, "max_tokens": 300},
                "openai5": {"uri": "https://litellm.oit.duke.edu/v1/", "extra_params": {}},
            }
        }
        profile, generator_cfg = run_garak._resolve_generator_cfg(
            cfg, "Qwen/Qwen2.5-3B-Instruct", "http://gpu-node:8000/v1"
        )
        self.assertEqual(profile, "base-url")
        self.assertEqual(generator_cfg["uri"], "http://gpu-node:8000/v1")
        # non-uri fields still come from the "standard" profile defaults
        self.assertEqual(generator_cfg["temperature"], 0)
        self.assertEqual(generator_cfg["max_tokens"], 300)

    def test_base_url_defaults_api_key_env_var_when_unset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config_file = tmp_path / "garak_duke.yaml"
            config_file.write_text(
                yaml.dump(
                    {
                        "_generator_profiles": {
                            "standard": {"uri": "https://litellm.oit.duke.edu/v1/"},
                            "openai5": {"uri": "https://litellm.oit.duke.edu/v1/"},
                        },
                        "plugins": {
                            "generators": {"openai": {}},
                            "probe_spec": DUKE14_PROBE_SPEC,
                        },
                    }
                ),
                encoding="utf-8",
            )
            captured: dict[str, object] = {}

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                # run_garak deletes the temp config in a `finally` right after this
                # call returns, so read it now while it still exists on disk.
                config_arg = cmd[cmd.index("--config") + 1]
                captured["written_cfg"] = yaml.safe_load(Path(config_arg).read_text(encoding="utf-8"))
                return mock.Mock(returncode=0)

            with mock.patch.object(run_garak, "CONFIG_FILE", config_file), \
                 mock.patch.object(run_garak, "_prefetch_hf_models", lambda: None), \
                 mock.patch.object(run_garak, "_prefetch_toxic_detector", lambda: None), \
                 mock.patch.object(run_garak, "_validate_probe_spec", return_value=(14, 62)), \
                 mock.patch.object(run_garak.subprocess, "run", side_effect=fake_run), \
                 mock.patch.dict(run_garak.os.environ, {}, clear=False), \
                 mock.patch("sys.argv", [
                     "run_garak.py", "Qwen/Qwen2.5-3B-Instruct",
                     "--base-url", "http://gpu-node:8000/v1",
                 ]):
                run_garak.os.environ.pop("OPENAICOMPATIBLE_API_KEY", None)
                exit_code = run_garak.main()
                # must assert before mock.patch.dict restores the original environ on exit
                self.assertTrue(run_garak.os.environ.get("OPENAICOMPATIBLE_API_KEY"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                captured["written_cfg"]["plugins"]["generators"]["openai"]["OpenAICompatible"]["uri"],
                "http://gpu-node:8000/v1",
            )

    def test_duke_probe_spec_in_yaml(self) -> None:
        cfg = yaml.safe_load(run_garak.CONFIG_FILE.read_text(encoding="utf-8"))
        probe_spec = cfg["plugins"]["probe_spec"]
        self.assertTrue(probe_spec)
        self.assertNotIn("propile", probe_spec)
        self.assertNotIn("realtoxicityprompts", probe_spec)

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
