"""
Tests for the safety-run launcher's Hugging Face model path.

/safety/new lets you run a gateway model OR specify an HF model. The HF path
validates the repo (safety/hf_preflight) before any run; with a server
endpoint it launches for real (policy/garak, and red-team if an
attack-generator endpoint is also given — see HfLaunchWithAttackerTest);
without one it only validates, mirroring the evaluator's existing HF launch
path (test_eval_hf_launch.py). All offline (the HF Hub validation is mocked).

Run from repo root:
  uv run python -m unittest unit_tests.test_safety_hf_launch -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from evaluator import hf_intake  # noqa: E402
from frontend import create_app, safety_launch  # noqa: E402


def _isolate_safety_output(test_case: unittest.TestCase) -> Path:
    """See test_safety_launch._isolate_safety_output — same rationale."""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    patcher = mock.patch.object(safety_launch, "ROOT", root)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    test_case.addCleanup(safety_launch._RUNNING.clear)
    test_case.addCleanup(safety_launch._INFLIGHT.clear)
    return root


_GOOD = hf_intake.ValidationResult(
    True, None,
    hf_intake.ModelInfo(repo_id="Qwen/Qwen2.5-7B-Instruct",
                        architectures=["Qwen2ForCausalLM"],
                        num_params=7_000_000_000, gated=False))
_BAD = hf_intake.ValidationResult(
    False, "model is gated/private; not supported in the MVP")


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        _isolate_safety_output(self)
        # Keep the gateway model list offline/deterministic (no gateway call).
        p = mock.patch.object(safety_launch, "_eligible_gateway_models",
                              return_value=safety_launch._GATEWAY_FALLBACK)
        p.start()
        self.addCleanup(p.stop)
        # /safety/new and /safety/start require a signed-in, allowlisted user —
        # force the dev-auth bypass on regardless of the real .env AUTH_ENABLED.
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = create_app({"TESTING": True}).test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}


class HfLaunchFormTest(_Base):
    def test_new_page_offers_gateway_and_hf_sources(self) -> None:
        r = self.client.get("/safety/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'name="hf_repo"', r.data)        # the HF field
        self.assertIn(b'name="source"', r.data)         # gateway/hf toggle
        self.assertIn(b'name="gateway_model"', r.data)  # gateway dropdown still there

    def test_new_page_shows_mandatory_attacker_model(self) -> None:
        # No attacker_repo field — the model is fixed, not user input; only
        # its endpoint is ever asked for.
        r = self.client.get("/safety/new")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b'name="attacker_repo"', r.data)
        self.assertIn(b'name="attacker_endpoint"', r.data)
        self.assertIn(safety_launch.MANDATORY_ATTACKER_REPO.encode(), r.data)


class HfLaunchValidateTest(_Base):
    def test_validate_hf_candidate_wraps_hf_preflight(self) -> None:
        # safety_launch.validate_hf_candidate delegates to safety.hf_preflight,
        # which itself calls evaluator's shared hf_intake.validate — mock at
        # that shared layer, same as the evaluator's own test does.
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD):
            out = safety_launch.validate_hf_candidate("Qwen/Qwen2.5-7B-Instruct")
        self.assertTrue(out["ok"])
        self.assertEqual(out["architectures"], ["Qwen2ForCausalLM"])
        self.assertEqual(out["repo_id"], "Qwen/Qwen2.5-7B-Instruct")

    def test_post_hf_valid_shows_ready(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD):
            r = self.client.post("/safety/start",
                                 data={"source": "hf",
                                       "hf_repo": "Qwen/Qwen2.5-7B-Instruct"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Qwen2ForCausalLM", r.data)

    def test_post_hf_invalid_shows_reason(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_BAD):
            r = self.client.post("/safety/start",
                                 data={"source": "hf", "hf_repo": "org/gated"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gated", r.data)

    def test_post_hf_does_not_start_a_run(self) -> None:
        # No endpoint to scan against yet — the HF path validates only, never
        # spawning a runner, exactly like the evaluator's HF path.
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(safety_launch, "start_run") as sr:
            self.client.post("/safety/start",
                           data={"source": "hf",
                                 "hf_repo": "Qwen/Qwen2.5-7B-Instruct"})
        sr.assert_not_called()

    def test_post_gateway_still_starts_a_run(self) -> None:
        # Regression: the gateway path is unchanged by the HF branch.
        with mock.patch.object(safety_launch, "start_run",
                               return_value=("gpt-5.5/base", False, "public")) as sr, \
             mock.patch.object(safety_launch, "validate_launch", return_value=None):
            r = self.client.post(
                "/safety/start",
                data={"gateway_model": "gpt-5.5", "run_policy": "1",
                      "run_redteam": "1", "run_garak": "1"})
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()


class HfLaunchWithEndpointTest(_Base):
    """An hf_endpoint value switches the HF path from validate-only to
    actually launching a scan (still red-team-off, unlike the gateway path)."""

    def test_post_hf_with_endpoint_launches_and_redirects(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(safety_launch, "start_run",
                               return_value=("qwen__qwen2.5-7b-instruct/base", False, "private")) as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                "hf_endpoint": "http://gpu-node:8000/v1",
                "run_policy": "1",
                "run_garak": "1",
            })
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()
        _args, kwargs = sr.call_args
        self.assertEqual(kwargs["hf_repo"], "Qwen/Qwen2.5-7B-Instruct")
        self.assertEqual(kwargs["endpoint"], "http://gpu-node:8000/v1")
        self.assertFalse(kwargs["skip_policy"])
        self.assertFalse(kwargs["skip_garak"])

    def test_post_hf_with_endpoint_invalid_repo_rejected(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_BAD), \
             mock.patch.object(safety_launch, "start_run") as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "org/gated",
                "hf_endpoint": "http://gpu-node:8000/v1",
                "run_policy": "1",
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"gated", r.data)
        sr.assert_not_called()

    def test_post_hf_with_endpoint_no_suites_rejected(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(safety_launch, "start_run") as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                "hf_endpoint": "http://gpu-node:8000/v1",
                # neither run_policy nor run_garak submitted
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"at least one suite", r.data)
        sr.assert_not_called()


class HfLaunchWithAttackerTest(_Base):
    """Red-team for an HF target needs the (fixed) attacker's endpoint —
    never reuses the target — plus a real Duke key for the grader regardless."""

    def test_post_hf_redteam_with_attacker_launches(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.dict(os.environ, {"OPENAI_API_KEY": "real-duke-key"}), \
             mock.patch.object(safety_launch, "start_run",
                               return_value=("qwen__qwen2.5-7b-instruct/base", False, "private")) as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                "hf_endpoint": "http://gpu-node:8000/v1",
                "run_policy": "1",
                "run_redteam": "1",
                "attacker_endpoint": "http://attacker-node:8001/v1",
            })
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()
        _args, kwargs = sr.call_args
        self.assertFalse(kwargs["skip_redteam"])
        self.assertEqual(kwargs["attacker_endpoint"], "http://attacker-node:8001/v1")
        self.assertNotIn("attacker_repo", kwargs)  # no longer a parameter at all

    def test_post_hf_redteam_without_attacker_endpoint_rejected(self) -> None:
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.dict(os.environ, {"OPENAI_API_KEY": "real-duke-key"}), \
             mock.patch.object(safety_launch, "start_run") as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                "hf_endpoint": "http://gpu-node:8000/v1",
                "run_redteam": "1",
                # no attacker_endpoint submitted
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"attack-generator", r.data)
        sr.assert_not_called()

    def test_post_hf_redteam_without_real_key_rejected(self) -> None:
        # An empty string, not a popped key: @require_login's auth check
        # calls load_repo_env() (dotenv override=False) on every request,
        # which would silently re-populate a *missing* key from this
        # sandbox's real .env before the route body ever runs — an empty
        # string still "exists" for dotenv's purposes, so it survives.
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.dict(os.environ, {"OPENAI_API_KEY": ""}), \
             mock.patch.object(safety_launch, "start_run") as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                "hf_endpoint": "http://gpu-node:8000/v1",
                "run_redteam": "1",
                "attacker_endpoint": "http://attacker-node:8001/v1",
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"OPENAI_API_KEY", r.data)
        sr.assert_not_called()

    def test_post_hf_without_redteam_ignores_leftover_attacker_endpoint(self) -> None:
        # Regression: an attacker endpoint present but red-team not checked
        # should behave exactly like a plain policy/garak-only HF launch.
        with mock.patch.object(hf_intake, "validate", return_value=_GOOD), \
             mock.patch.object(safety_launch, "start_run",
                               return_value=("qwen__qwen2.5-7b-instruct/base", False, "private")) as sr:
            r = self.client.post("/safety/start", data={
                "source": "hf",
                "hf_repo": "Qwen/Qwen2.5-7B-Instruct",
                "hf_endpoint": "http://gpu-node:8000/v1",
                "run_policy": "1",
                "attacker_endpoint": "http://attacker-node:8001/v1",
            })
        self.assertEqual(r.status_code, 302)
        _args, kwargs = sr.call_args
        self.assertTrue(kwargs["skip_redteam"])


class ValidateHfLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        # test_redteam_with_everything_valid_passes reaches _prepare_output_dirs
        # (nothing earlier rejects it) — isolate so it doesn't touch the real repo.
        _isolate_safety_output(self)

    def test_requires_endpoint(self) -> None:
        err = safety_launch.validate_hf_launch("org/model", "")
        self.assertIn("endpoint", err)

    def test_requires_at_least_one_suite(self) -> None:
        err = safety_launch.validate_hf_launch(
            "org/model", "http://gpu-node:8000/v1",
            skip_policy=True, skip_garak=True,
        )
        self.assertIn("at least one suite", err)

    def test_redteam_alone_satisfies_at_least_one_suite(self) -> None:
        # skip_policy=skip_garak=True is fine as long as redteam is requested —
        # it fails later (missing attacker fields), not on the suite check.
        err = safety_launch.validate_hf_launch(
            "org/model", "http://gpu-node:8000/v1",
            skip_policy=True, skip_garak=True, redteam=True,
        )
        self.assertNotIn("at least one suite", err or "")

    def test_redteam_requires_attacker_endpoint(self) -> None:
        # No attacker_repo to supply anymore — the model is fixed
        # (MANDATORY_ATTACKER_REPO); only its endpoint is ever asked for.
        err = safety_launch.validate_hf_launch(
            "org/model", "http://gpu-node:8000/v1", redteam=True,
        )
        self.assertIn("attack-generator", err)
        self.assertIn(safety_launch.MANDATORY_ATTACKER_REPO, err)

    def test_redteam_requires_real_api_key(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            err = safety_launch.validate_hf_launch(
                "org/model", "http://gpu-node:8000/v1", redteam=True,
                attacker_endpoint="http://attacker:8001/v1",
            )
        self.assertIn("OPENAI_API_KEY", err)

    def test_redteam_with_everything_valid_passes(self) -> None:
        good = hf_intake.ValidationResult(
            True, None,
            hf_intake.ModelInfo(repo_id="org/model", architectures=["Qwen2ForCausalLM"],
                                num_params=3_000_000_000, gated=False))
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "real-duke-key"}), \
             mock.patch.object(hf_intake, "validate", return_value=good):
            err = safety_launch.validate_hf_launch(
                "org/model", "http://gpu-node:8000/v1", redteam=True,
                attacker_endpoint="http://attacker:8001/v1",
            )
        self.assertIsNone(err)


class BuildCommandHfTest(unittest.TestCase):
    def test_hf_command_uses_hf_repo_and_endpoint_flags(self) -> None:
        cmd = safety_launch.build_command(
            "Qwen/Qwen2.5-7B-Instruct",
            hf_repo="Qwen/Qwen2.5-7B-Instruct",
            endpoint="http://gpu-node:8000/v1",
        )
        cmd_str = " ".join(cmd)
        self.assertIn("--hf-repo", cmd)
        self.assertIn("--endpoint", cmd)
        self.assertIn("--skip-redteam", cmd_str)

    def test_hf_command_forces_skip_redteam_even_if_not_requested(self) -> None:
        cmd = safety_launch.build_command(
            "Qwen/Qwen2.5-7B-Instruct",
            skip_redteam=False,
            hf_repo="Qwen/Qwen2.5-7B-Instruct",
            endpoint="http://gpu-node:8000/v1",
        )
        self.assertIn("--skip-redteam", cmd)

    def test_hf_docker_env_never_sets_grader_to_hf_repo(self) -> None:
        # The real gap this guards against: sending a nonexistent model name
        # to Duke's real gateway for grading (see safety/run.py's own note).
        with mock.patch.object(safety_launch.docker_launch, "use_docker", return_value=True):
            cmd = safety_launch.build_command(
                "Qwen/Qwen2.5-7B-Instruct",
                hf_repo="Qwen/Qwen2.5-7B-Instruct",
                endpoint="http://gpu-node:8000/v1",
            )
        self.assertIn("-e", cmd)
        self.assertIn("GATEWAY_MODEL=Qwen/Qwen2.5-7B-Instruct", cmd)
        self.assertNotIn("REDTEAM_GRADER_MODEL=Qwen/Qwen2.5-7B-Instruct", cmd)

    def test_gateway_docker_env_still_sets_grader_to_model(self) -> None:
        # Regression: the gateway path's existing behavior is unchanged.
        with mock.patch.object(safety_launch.docker_launch, "use_docker", return_value=True):
            cmd = safety_launch.build_command("gpt-5.5")
        self.assertIn("REDTEAM_GRADER_MODEL=gpt-5.5", cmd)

    def test_hf_command_with_attacker_endpoint_does_not_force_skip_redteam(self) -> None:
        cmd = safety_launch.build_command(
            "Qwen/Qwen2.5-7B-Instruct",
            skip_redteam=False,
            hf_repo="Qwen/Qwen2.5-7B-Instruct",
            endpoint="http://gpu-node:8000/v1",
            attacker_endpoint="http://attacker-node:8001/v1",
        )
        self.assertNotIn("--skip-redteam", cmd)
        self.assertIn("--attacker-repo", cmd)
        self.assertIn("--attacker-endpoint", cmd)
        idx = cmd.index("--attacker-repo")
        # Always the mandatory constant — build_command never trusts caller
        # input for this, there being no such input to trust anymore.
        self.assertEqual(cmd[idx + 1], safety_launch.MANDATORY_ATTACKER_REPO)


if __name__ == "__main__":
    unittest.main()
