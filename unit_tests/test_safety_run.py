"""Unit tests for safety.run pipeline helpers."""

from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr
from unittest import mock

from evaluator import hf_intake
from safety.run import (
    RunConfig,
    _export_promptfoo_eval,
    _resolve_attacker_target,
    _resolve_hf_target,
    garak_xdg_env,
    parse_args,
    run_pipeline,
)


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

    def test_hf_repo_and_endpoint_parsed(self) -> None:
        sub, cfg = parse_args([
            "--hf-repo", "Qwen/Qwen2.5-3B-Instruct",
            "--endpoint", "http://gpu-node:8000/v1",
            "--skip-redteam",
        ])
        self.assertIsNone(sub)
        self.assertEqual(cfg.hf_repo, "Qwen/Qwen2.5-3B-Instruct")
        self.assertEqual(cfg.base_url, "http://gpu-node:8000/v1")
        # --hf-repo also becomes the model id sent to garak/promptfoo
        self.assertEqual(cfg.model, "Qwen/Qwen2.5-3B-Instruct")

    def test_hf_repo_overrides_positional_model(self) -> None:
        sub, cfg = parse_args(["GPT 4.1 Mini", "--hf-repo", "Qwen/Qwen2.5-3B-Instruct"])
        self.assertIsNone(sub)
        self.assertEqual(cfg.model, "Qwen/Qwen2.5-3B-Instruct")

    def test_attacker_repo_and_endpoint_parsed(self) -> None:
        sub, cfg = parse_args([
            "--hf-repo", "Qwen/Qwen2.5-3B-Instruct", "--endpoint", "http://target:8000/v1",
            "--attacker-repo", "huihui-ai/Qwen2.5-7B-Instruct-abliterated-v2",
            "--attacker-endpoint", "http://attacker:8001/v1",
        ])
        self.assertIsNone(sub)
        self.assertEqual(cfg.attacker_repo, "huihui-ai/Qwen2.5-7B-Instruct-abliterated-v2")
        self.assertEqual(cfg.attacker_base_url, "http://attacker:8001/v1")


class ExportPromptfooEvalIncompleteTest(unittest.TestCase):
    """A promptfoo subprocess that crashes but still leaves a partial
    eval.json must be exported with process_complete=False (--incomplete),
    not presented as a clean, fully-weighted suite — see safety.exporters
    .promptfoo's process_complete field and frontend.safety_launch's
    _promptfoo_partial_warnings."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.eval_json = Path(tmp.name) / "eval.json"
        self.eval_json.write_text("{}", encoding="utf-8")

    def test_incomplete_true_passes_incomplete_flag(self) -> None:
        with mock.patch("safety.run.run_py") as run_py:
            rc = _export_promptfoo_eval(self.eval_json, label="policy eval", incomplete=True)
        self.assertIsNone(rc)
        argv = run_py.call_args.args[0]
        self.assertIn("--incomplete", argv)

    def test_incomplete_false_omits_flag(self) -> None:
        with mock.patch("safety.run.run_py") as run_py:
            rc = _export_promptfoo_eval(self.eval_json, label="policy eval")
        self.assertIsNone(rc)
        argv = run_py.call_args.args[0]
        self.assertNotIn("--incomplete", argv)


class GarakXdgEnvTest(unittest.TestCase):
    def test_creates_dirs_and_returns_env(self) -> None:
        env = garak_xdg_env("test-slug-xdg")
        self.assertIn("HOME", env)
        self.assertIn("test-slug-xdg", env["HOME"])
        self.assertEqual(env["USER"], "garak")
        self.assertEqual(env["LOGNAME"], "garak")
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

    def test_blocks_when_garak_slug_lock_held_by_other_profile(self) -> None:
        """Garak's output tree has no per-profile subdirectory (one shared
        tree per model slug), so a second, different-profile run must not
        proceed while another profile's run is still using Garak for the
        same model — even though its own per-profile lock is free."""
        from unittest import mock

        cfg = RunConfig(model="GPT 4.1 Mini", redteam_profile="healthcare", skip_garak=False, redteam=False)

        def fake_try_acquire(path, **_kwargs):
            # The per-profile lock (safety/output/<slug>/<profile>/run.lock)
            # is free; the shared per-slug garak lock is held by the other
            # profile's run.
            return "garak" not in str(path)

        with mock.patch("safety.run.run_lock.should_skip_cli_acquire", return_value=False), mock.patch(
            "safety.run.run_lock.try_acquire", side_effect=fake_try_acquire
        ), mock.patch("safety.run.run_lock.release") as release, mock.patch(
            "safety.run._run_pipeline_impl"
        ) as impl:
            self.assertEqual(run_pipeline(cfg), 2)

        impl.assert_not_called()
        # The per-profile lock it did manage to claim must be released again
        # rather than left dangling now that the run isn't proceeding.
        release.assert_called_once()

    def test_skip_garak_never_touches_garak_lock(self) -> None:
        from unittest import mock

        cfg = RunConfig(model="GPT 4.1 Mini", redteam_profile="base", skip_garak=True, redteam=False)
        with mock.patch("safety.run.run_lock.should_skip_cli_acquire", return_value=False), mock.patch(
            "safety.run.run_lock.try_acquire", return_value=True
        ) as acquire, mock.patch("safety.run.run_lock.release"), mock.patch(
            "safety.run._run_pipeline_impl", return_value=0
        ):
            self.assertEqual(run_pipeline(cfg), 0)

        # Only the per-profile lock — never a garak-slug lock — is touched
        # when this run isn't using Garak at all.
        self.assertEqual(acquire.call_count, 1)
        self.assertNotIn("garak", str(acquire.call_args.args[0]))

    def test_rejects_hf_repo_with_redteam_and_no_real_key(self) -> None:
        # redteam defaults to True; the grader always stays on Duke and needs a
        # real key regardless of target — block only when none is configured.
        cfg = RunConfig(model="org/model", hf_repo="org/model")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            self.assertEqual(run_pipeline(cfg), 1)

    def test_allows_hf_repo_with_redteam_when_real_key_present(self) -> None:
        # With a real key set, --hf-repo + redteam is no longer blocked outright.
        # Uses a deliberately invalid repo id so it fails at preflight instead —
        # a different, distinguishable error from the redteam/key block.
        cfg = RunConfig(model="a;rm -rf /", hf_repo="a;rm -rf /")
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "real-duke-key"}):
            with redirect_stderr(err):
                code = run_pipeline(cfg)
        self.assertEqual(code, 1)
        self.assertIn("pre-flight validation", err.getvalue())
        self.assertNotIn("red-team grading needs", err.getvalue())

    def test_hf_repo_with_redteam_disabled_reaches_preflight(self) -> None:
        # No mocking of hf_preflight here: an invalid repo id fails the
        # allowlist offline, so this proves the hf_repo path is actually
        # reached (not silently skipped) without touching the network.
        cfg = RunConfig(model="a;rm -rf /", hf_repo="a;rm -rf /", redteam=False, skip_garak=True)
        self.assertEqual(run_pipeline(cfg), 1)

    def test_attacker_repo_requires_endpoint(self) -> None:
        # A valid-looking attacker repo id (mocked so no network call happens)
        # with no --attacker-endpoint must be rejected before anything else runs.
        canned = hf_intake.ValidationResult(True, None, _hf_info(repo_id="org/attacker"))
        cfg = RunConfig(
            model="a;rm -rf /", hf_repo="a;rm -rf /", redteam=False, skip_garak=True,
            attacker_repo="org/attacker",
        )
        err = io.StringIO()
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            with redirect_stderr(err):
                code = run_pipeline(cfg)
        self.assertEqual(code, 1)
        self.assertIn("--attacker-repo requires --attacker-endpoint", err.getvalue())


def _hf_info(**kw) -> hf_intake.ModelInfo:
    base = dict(repo_id="org/model", architectures=["Qwen2ForCausalLM"],
                num_params=3_000_000_000, gated=False)
    base.update(kw)
    return hf_intake.ModelInfo(**base)


class ResolveHfTargetTest(unittest.TestCase):
    def test_invalid_repo_id_returns_none(self) -> None:
        self.assertIsNone(_resolve_hf_target("a;rm -rf /", ""))

    def test_explicit_endpoint_skips_dcc_state(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _hf_info())
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            result = _resolve_hf_target("org/model", "http://gpu-node:8000/v1")
        self.assertEqual(result, "http://gpu-node:8000/v1")

    def test_no_endpoint_no_session_returns_none(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _hf_info())
        with mock.patch.object(hf_intake, "validate", return_value=canned), \
             mock.patch("safety.run.dcc_vllm._read_state", side_effect=FileNotFoundError):
            result = _resolve_hf_target("org/model", "")
        self.assertIsNone(result)

    def test_session_without_host_returns_none(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _hf_info())
        with mock.patch.object(hf_intake, "validate", return_value=canned), \
             mock.patch("safety.run.dcc_vllm._read_state", return_value={"PORT": "8000"}):
            result = _resolve_hf_target("org/model", "")
        self.assertIsNone(result)

    def test_session_with_host_builds_url(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _hf_info())
        with mock.patch.object(hf_intake, "validate", return_value=canned), \
             mock.patch(
                 "safety.run.dcc_vllm._read_state",
                 return_value={"HOST": "gpu-node-42", "PORT": "8000"},
             ):
            result = _resolve_hf_target("org/model", "")
        self.assertEqual(result, "http://gpu-node-42:8000/v1")


class ResolveAttackerTargetTest(unittest.TestCase):
    def test_invalid_repo_id_returns_none(self) -> None:
        self.assertIsNone(_resolve_attacker_target("a;rm -rf /", "http://attacker:8001/v1"))

    def test_valid_repo_no_endpoint_returns_none(self) -> None:
        # No DCC-session fallback for the attacker — an endpoint must be explicit.
        canned = hf_intake.ValidationResult(True, None, _hf_info())
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            result = _resolve_attacker_target("org/model", "")
        self.assertIsNone(result)

    def test_valid_repo_with_endpoint_returns_it(self) -> None:
        canned = hf_intake.ValidationResult(True, None, _hf_info())
        with mock.patch.object(hf_intake, "validate", return_value=canned):
            result = _resolve_attacker_target("org/model", "http://attacker:8001/v1")
        self.assertEqual(result, "http://attacker:8001/v1")


if __name__ == "__main__":
    unittest.main()
