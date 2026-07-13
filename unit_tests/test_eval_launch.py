"""
Tests for the live "Start run" flow — no subprocess spawn, no API calls.

The security-critical path is allowlist validation in eval_launch +
the 400 behavior of POST /eval-run/start: nothing outside the allowlist
may ever reach subprocess.Popen.

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_launch -v
"""

from __future__ import annotations

import os

# Browser launches default to Docker; unit tests exercise the host argv path.
# Force (don't setdefault) so a developer .env with FRONTEND_LAUNCH_MODE=docker
# cannot break spawn tests that patch subprocess.Popen.
os.environ["FRONTEND_LAUNCH_MODE"] = "host"

import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from frontend import create_app
from frontend import eval_launch


def _alive_proc(*, pid: int = 4242) -> mock.Mock:
    """Mock Popen that stays in-flight for watch-thread / dedupe tests.

    ``Mock.wait()`` returns immediately by default, which lets the new
    run-lock watch thread clear ``_RUNNING`` before a duplicate POST.
    """
    proc = mock.Mock()
    proc.poll.return_value = None
    proc.pid = pid
    proc.wait = mock.Mock(side_effect=lambda *a, **k: threading.Event().wait(timeout=60))
    return proc


def _isolate_eval_output(test_case: unittest.TestCase) -> Path:
    """Redirect eval_launch.RESULTS_DIR to a scratch tempdir and reset its
    in-memory run registry — see test_scan_launch._isolate_scan_output for
    why (a real, unmocked launch path writes real files under
    evaluator/results/ and populates eval_launch._RUNNING/_INFLIGHT for
    real, cleaned up on an unsynchronized background thread)."""
    tmp = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmp.cleanup)
    root = Path(tmp.name)
    patcher = mock.patch.object(eval_launch, "RESULTS_DIR", root)
    patcher.start()
    test_case.addCleanup(patcher.stop)
    test_case.addCleanup(eval_launch._RUNNING.clear)
    test_case.addCleanup(eval_launch._INFLIGHT.clear)
    return root


class ValidateLaunchTest(unittest.TestCase):
    def setUp(self) -> None:
        # Keep unit tests offline + deterministic: the candidate allowlist is
        # normally the live gateway catalog, but here we pin it to the curated
        # priced set (avoids a network call — and the OpenAI client's uname
        # subprocess — on the validate path).
        patcher = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_valid_combo_passes(self) -> None:
        self.assertIsNone(
            eval_launch.validate_launch(
                "gpt-5-chat", "Llama 4 Maverick", "it_support_v1", 500
            )
        )

    def test_unknown_candidate_rejected(self) -> None:
        err = eval_launch.validate_launch(
            "rm -rf /", "Llama 4 Maverick", "it_support_v1", 500
        )
        self.assertIn("candidate model not in allowlist", err)

    def test_unknown_judge_rejected(self) -> None:
        err = eval_launch.validate_launch(
            "gpt-5-chat", "evil-judge; echo pwned", "it_support_v1", 500
        )
        self.assertIn("judge model not in allowlist", err)

    def test_same_family_judge_rejected(self) -> None:
        # gpt-oss-120b is OpenAI-family, like gpt-5-chat — cross-family rule
        err = eval_launch.validate_launch(
            "gpt-5-chat", "gpt-oss-120b", "it_support_v1", 500
        )
        self.assertIn("same model family", err)

    def test_llama_candidate_with_llama_judge_rejected(self) -> None:
        err = eval_launch.validate_launch(
            "Llama 4 Scout", "Llama 4 Maverick", "it_support_v1", 500
        )
        self.assertIn("same model family", err)

    def test_llama_candidate_with_openai_judge_ok(self) -> None:
        self.assertIsNone(
            eval_launch.validate_launch(
                "Llama 4 Scout", "gpt-oss-120b", "it_support_v1", 500
            )
        )

    def test_unknown_suite_rejected(self) -> None:
        err = eval_launch.validate_launch(
            "gpt-5-chat", "Llama 4 Maverick", "../../etc/passwd", 500
        )
        self.assertIn("unknown suite", err)

    def test_max_tokens_bounds(self) -> None:
        for bad in (0, 49, 4001, -5):
            err = eval_launch.validate_launch(
                "gpt-5-chat", "Llama 4 Maverick", "it_support_v1", bad
            )
            self.assertIn("max_tokens", err, f"max_tokens={bad} should be rejected")

    def test_hub_style_llama_candidate_still_rejected(self) -> None:
        # Regression: a Llama candidate whose id does NOT start with "llama"
        # (a Hub-style "meta-llama/Llama-4-Scout") must still classify as meta,
        # so the Llama judge is correctly rejected as same-family. A naive
        # startswith() check let this exact pair slip through.
        hub_id = "meta-llama/Llama-4-Scout"
        with mock.patch.object(eval_launch, "candidate_models",
                               return_value=(*eval_launch._CANDIDATE_FALLBACK, hub_id)):
            err = eval_launch.validate_launch(
                hub_id, "Llama 4 Maverick", "it_support_v1", 500)
        self.assertIn("same model family", err)


class ModelFamilyTest(unittest.TestCase):
    def test_llama_variants_classify_as_meta(self) -> None:
        for s in ("Llama 4 Maverick", "meta-llama/Llama-4-Scout",
                  "Meta-Llama-3.1-8B", "llama-3.3-70b"):
            self.assertEqual(eval_launch.model_family(s), "meta", s)

    def test_openai_and_qwen_families(self) -> None:
        self.assertEqual(eval_launch.model_family("gpt-5-chat"), "openai")
        self.assertEqual(eval_launch.model_family("gpt-oss-120b"), "openai")
        self.assertEqual(eval_launch.model_family("Qwen/Qwen2.5-7B-Instruct"), "qwen")


class SuiteMetadataTest(unittest.TestCase):
    """Each task suite carries a plain-language description + example question,
    surfaced by get_launch_options for the on-page suite tooltips."""

    def setUp(self) -> None:
        patcher = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_suite_has_description_and_example(self) -> None:
        for key, cfg in eval_launch.SUITES.items():
            self.assertTrue(cfg.get("description"), f"{key} missing description")
            self.assertTrue(cfg.get("example"), f"{key} missing example")

    def test_launch_options_surfaces_suite_blurbs(self) -> None:
        opts = eval_launch.get_launch_options()
        self.assertTrue(opts["suites"])
        for s in opts["suites"]:
            self.assertTrue(s.get("description"), f"{s['key']} blurb missing")
            self.assertTrue(s.get("example"), f"{s['key']} example missing")


# Suites whose answer is checked by RUNNING it (execution_eval), not by the LLM
# judge. The runner auto-skips the judge for these (scoring=execution).
_EXPECTED_EXECUTION_SUITES = frozenset(
    {"sql_duke_v2", "json_duke_v1", "numeric_duke_v1"})


class SuiteCoverageTest(unittest.TestCase):
    """The launch form must surface the execution-scored suites (so the Exec
    column has runs to show) alongside the judge suites, and every suite must
    declare a scoring type with contract files that actually resolve."""

    def setUp(self) -> None:
        patcher = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_execution_suites_present_and_marked(self) -> None:
        for key in _EXPECTED_EXECUTION_SUITES:
            self.assertIn(key, eval_launch.SUITES, f"{key} not surfaced")
            self.assertEqual(eval_launch.SUITES[key].get("scoring"), "execution",
                             f"{key} not marked scoring=execution")

    def test_every_suite_declares_a_known_scoring_type(self) -> None:
        for key, cfg in eval_launch.SUITES.items():
            self.assertIn(cfg.get("scoring"), ("judge", "execution"),
                          f"{key} missing/invalid scoring")

    def test_every_suite_contract_file_resolves(self) -> None:
        # Guards against a typo'd rubric/prompt path — build_command reads all
        # three, so a missing file would crash the launch (not the judge-skip).
        for key, cfg in eval_launch.SUITES.items():
            for field in ("suite", "rubric", "system_prompt"):
                self.assertTrue(cfg[field].is_file(),
                                f"{key}.{field} does not exist: {cfg[field]}")

    def test_launch_options_surfaces_scoring(self) -> None:
        by_key = {s["key"]: s.get("scoring")
                  for s in eval_launch.get_launch_options()["suites"]}
        self.assertEqual(by_key.get("sql_duke_v2"), "execution")
        self.assertEqual(by_key.get("it_support_v1"), "judge")

    def test_build_command_targets_the_execution_suite_file(self) -> None:
        cmd = eval_launch.build_command(
            "gpt-5-chat", "Llama 4 Maverick", "sql_duke_v2", 500, "stemX")
        self.assertIn("--suite", cmd)
        self.assertIn("sql_duke_v2", cmd[cmd.index("--suite") + 1])


class BuildCommandTest(unittest.TestCase):
    def test_command_is_argv_list_with_expected_flags(self) -> None:
        cmd = eval_launch.build_command(
            "gpt-5-chat", "Llama 4 Maverick", "policy_qa_v1.1", 500, "stem123"
        )
        self.assertIsInstance(cmd, list)
        self.assertIn("--candidate-model", cmd)
        self.assertIn("--output-name", cmd)
        self.assertEqual(cmd[cmd.index("--output-name") + 1], "stem123")
        # rubric-aware judge prompt always — avoids the runner's fail-fast
        prompt = cmd[cmd.index("--judge-prompt") + 1]
        self.assertIn("reference_based_v2", prompt)
        rubric = cmd[cmd.index("--rubric") + 1]
        self.assertIn("policy_qa_v1", rubric)

    def test_predicted_stem_matches_runner_convention(self) -> None:
        stem = eval_launch.predict_stem("it_support_v1", "Llama 4 Maverick")
        self.assertRegex(
            stem, r"^\d{8}T\d{6}Z_it_support_v1_Llama-4-Maverick$"
        )
        # stem must be slug-safe (the detail URL embeds it)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9._-]+", stem))


class GetStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(
            eval_launch, "RESULTS_DIR", Path(self._tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = Path(self._tmp.name)

    def test_unsafe_slug_is_not_found(self) -> None:
        self.assertEqual(eval_launch.get_status("../../etc")["status"], "not_found")

    def test_missing_file_unregistered_is_not_found(self) -> None:
        s = eval_launch.get_status("20990101T000000Z_it_support_v1_x")
        self.assertEqual(s["status"], "not_found")

    def test_done_when_rows_match_suite_size(self) -> None:
        slug = "20990101T000000Z_it_support_v1_x"
        n = eval_launch.suite_question_count("it_support_v1")
        (self.dir / f"{slug}.jsonl").write_text("{}\n" * n, encoding="utf-8")
        s = eval_launch.get_status(slug)
        self.assertEqual(s["status"], "done")
        self.assertEqual(s["progress"], n)

    def test_running_while_registered_process_alive(self) -> None:
        slug = "20990101T000000Z_policy_qa_v1.1_x"
        (self.dir / f"{slug}.jsonl").write_text("{}\n", encoding="utf-8")
        proc = mock.Mock()
        proc.poll.return_value = None  # alive
        with mock.patch.dict(eval_launch._RUNNING, {slug: proc}):
            s = eval_launch.get_status(slug)
        self.assertEqual(s["status"], "running")
        self.assertEqual(s["progress"], 1)

    def test_failed_when_process_exited_with_partial_file(self) -> None:
        slug = "20990101T000000Z_policy_qa_v1.1_x"
        (self.dir / f"{slug}.jsonl").write_text("{}\n", encoding="utf-8")
        proc = mock.Mock()
        proc.poll.return_value = 1  # exited
        with mock.patch.dict(eval_launch._RUNNING, {slug: proc}):
            s = eval_launch.get_status(slug)
        self.assertEqual(s["status"], "failed")


class LaunchRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        _isolate_eval_output(self)
        # Offline + deterministic candidate allowlist (see ValidateLaunchTest).
        # Also avoids the OpenAI client's platform/uname subprocess, which
        # would otherwise inflate the patched global subprocess.Popen count.
        patcher = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        # The gateway eval path now requires a cleared safety gate; keep the
        # existing spawn tests green by treating every model as cleared. The
        # block behavior is exercised in test_start_blocked_when_safety_missing.
        gate = mock.patch(
            "frontend.pipeline.require_ready_for_downstream", return_value=None
        )
        gate.start()
        self.addCleanup(gate.stop)
        # /eval-run/new and /eval-run/start require a signed-in, allowlisted
        # user — force the dev-auth bypass on regardless of the real .env
        # AUTH_ENABLED.
        env_patch = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = create_app({"TESTING": True}).test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}

    def test_form_renders(self) -> None:
        r = self.client.get("/eval-run/new")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"gpt-5-chat", r.data)
        self.assertIn(b"Llama 4 Maverick", r.data)

    def test_start_rejects_non_allowlisted_model(self) -> None:
        r = self.client.post("/eval-run/start", data={
            "candidate": "$(curl evil)", "judge": "Llama 4 Maverick",
            "suite": "it_support_v1", "max_tokens": "500",
        })
        self.assertEqual(r.status_code, 400)

    def test_start_rejects_non_integer_max_tokens(self) -> None:
        r = self.client.post("/eval-run/start", data={
            "candidate": "gpt-5-chat", "judge": "Llama 4 Maverick",
            "suite": "it_support_v1", "max_tokens": "lots",
        })
        self.assertEqual(r.status_code, 400)

    def test_start_valid_spawns_and_redirects(self) -> None:
        fake_proc = _alive_proc()
        with mock.patch.object(
            eval_launch.subprocess, "Popen", return_value=fake_proc
        ) as popen:
            r = self.client.post("/eval-run/start", data={
                "candidate": "GPT 4.1 Mini", "judge": "Llama 4 Maverick",
                "suite": "it_support_v1", "max_tokens": "500",
            })
        self.assertEqual(r.status_code, 302)
        self.assertIn("status=running", r.headers["Location"])
        popen.assert_called_once()
        argv = popen.call_args.args[0]
        self.assertIsInstance(argv, list)  # never a shell string
        self.assertIn("GPT 4.1 Mini", argv)

    def test_duplicate_start_returns_same_slug_without_second_spawn(self) -> None:
        fake_proc = _alive_proc()
        data = {
            "candidate": "gpt-5.1-chat", "judge": "Llama 4 Maverick",
            "suite": "policy_qa_v1.1", "max_tokens": "500",
        }
        with mock.patch.object(
            eval_launch.subprocess, "Popen", return_value=fake_proc
        ) as popen:
            r1 = self.client.post("/eval-run/start", data=data)
            r2 = self.client.post("/eval-run/start", data=data)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(r1.headers["Location"], r2.headers["Location"])

    def test_status_endpoint_returns_json(self) -> None:
        r = self.client.get("/eval-run/nonexistent-slug/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["status"], "not_found")

    def test_start_blocked_when_safety_missing(self) -> None:
        with mock.patch(
            "frontend.pipeline.require_ready_for_downstream",
            return_value="safety red-teaming required before this step",
        ), mock.patch.object(eval_launch.subprocess, "Popen") as popen:
            r = self.client.post("/eval-run/start", data={
                "candidate": "GPT 4.1 Mini", "judge": "Llama 4 Maverick",
                "suite": "it_support_v1", "max_tokens": "500",
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"safety red-teaming required", r.data)
        # The gate must short-circuit before any subprocess is spawned.
        popen.assert_not_called()

    def test_delete_requires_login(self) -> None:
        with self.client.session_transaction() as sess:
            sess.pop("user", None)
        r = self.client.get("/eval-run/nonexistent-slug/delete")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/login", r.headers["Location"])

    def test_private_detail_requires_login(self) -> None:
        with self.client.session_transaction() as sess:
            sess.pop("user", None)
        r = self.client.get("/eval-run/nonexistent-slug/private")
        self.assertIn(r.status_code, (302, 401, 403))


class CustomQuestionsTest(unittest.TestCase):
    """Custom 'bring your own' question sets — validation, suite writing,
    and resolution, with a temp custom-suites dir (no real files left behind)."""

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch.object(
            eval_launch, "CUSTOM_SUITES_DIR", Path(self._tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _good(self) -> str:
        import json
        return "\n".join(json.dumps(q) for q in [
            {"question": "Q1?", "reference": "A1"},
            {"question": "Q2?", "reference": "A2", "id": "my-2"},
        ])

    def test_valid_parse_assigns_ids(self) -> None:
        qs, err = eval_launch.validate_custom_questions(self._good())
        self.assertIsNone(err)
        self.assertEqual([q["id"] for q in qs], ["custom-001", "my-2"])

    def test_missing_reference_rejected(self) -> None:
        _, err = eval_launch.validate_custom_questions('{"question": "q"}')
        self.assertIn("reference", err)

    def test_bad_json_rejected(self) -> None:
        _, err = eval_launch.validate_custom_questions("not json")
        self.assertIn("not valid JSON", err)

    def test_empty_rejected(self) -> None:
        _, err = eval_launch.validate_custom_questions("   \n  ")
        self.assertIn("no questions", err)

    def test_too_many_rejected(self) -> None:
        import json
        many = "\n".join(
            json.dumps({"question": f"q{i}", "reference": "a"})
            for i in range(eval_launch.CUSTOM_MAX_QUESTIONS + 1)
        )
        _, err = eval_launch.validate_custom_questions(many)
        self.assertIn("too many", err)

    def test_oversized_field_rejected(self) -> None:
        import json
        big = json.dumps({"question": "x" * (eval_launch.CUSTOM_MAX_FIELD_CHARS + 1),
                          "reference": "a"})
        _, err = eval_launch.validate_custom_questions(big)
        self.assertIn("exceeds", err)

    def test_write_and_resolve(self) -> None:
        qs, _ = eval_launch.validate_custom_questions(self._good())
        key = eval_launch.write_custom_suite(qs)
        self.assertTrue(key.startswith("custom_"))
        self.assertIsNotNone(eval_launch._suite_cfg(key))
        self.assertEqual(eval_launch.suite_question_count(key), 2)
        self.assertIn(key, eval_launch._all_suite_keys())
        # marked ad-hoc in metadata
        import json
        meta = json.loads(
            (eval_launch.CUSTOM_SUITES_DIR / f"{key}.jsonl").read_text().splitlines()[0])
        self.assertTrue(meta["custom"])
        self.assertEqual(meta["task_suite_version"], key)

    def test_unknown_suite_still_rejected(self) -> None:
        self.assertIsNone(eval_launch._suite_cfg("custom_does_not_exist"))

    def test_build_command_targets_custom_file(self) -> None:
        qs, _ = eval_launch.validate_custom_questions(self._good())
        key = eval_launch.write_custom_suite(qs)
        cmd = eval_launch.build_command("gpt-5-chat", "Llama 4 Maverick", key, 500, "stem")
        self.assertTrue(any("custom" in str(c) for c in cmd))


class CustomRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        from pathlib import Path

        os.environ["AUTH_ENABLED"] = "0"
        os.environ["AUTH_DEV_NETID"] = "testuser"
        os.environ["AUTH_ALLOWED_NETIDS"] = "testuser"
        _isolate_eval_output(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for attr in ("CUSTOM_SUITES_DIR",):
            p = mock.patch.object(eval_launch, attr, Path(self._tmp.name))
            p.start()
            self.addCleanup(p.stop)
        cand = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK,
        )
        cand.start()
        self.addCleanup(cand.stop)
        gate = mock.patch(
            "frontend.pipeline.require_ready_for_downstream", return_value=None
        )
        gate.start()
        self.addCleanup(gate.stop)
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test"})
        self.client = self.app.test_client()
        with self.client.session_transaction() as sess:
            sess["view_mode"] = "private"
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}

    def test_invalid_questions_rejected(self) -> None:
        r = self.client.post("/eval-run/start-custom", data={
            "candidate": "gpt-5-chat", "judge": "Llama 4 Maverick",
            "max_tokens": "500", "questions": "not json",
        })
        self.assertEqual(r.status_code, 400)

    def test_valid_custom_spawns_and_redirects(self) -> None:
        fake = _alive_proc()
        with mock.patch.object(eval_launch.subprocess, "Popen", return_value=fake):
            r = self.client.post("/eval-run/start-custom", data={
                "candidate": "gpt-5-chat", "judge": "Llama 4 Maverick",
                "max_tokens": "500",
                "questions": '{"question": "Q?", "reference": "A"}',
            })
        self.assertEqual(r.status_code, 302)
        self.assertIn("custom_", r.headers["Location"])


class UnreadableEvalOutputTest(unittest.TestCase):
    def test_all_suite_keys_tolerates_unreadable_custom_dir(self) -> None:
        with mock.patch("dbutils.fs_safe.is_dir", return_value=False):
            keys = eval_launch._all_suite_keys()
        self.assertIn("it_support_v1", keys)

    def test_wipe_prior_runs_skips_unreadable_glob_match(self) -> None:
        root = _isolate_eval_output(self)
        good = root / "20260101_120000_gpt-5-chat_it-support.jsonl"
        good.write_text('{"x":1}\n', encoding="utf-8")

        real_glob = Path.glob

        def patched_glob(self, pattern):
            for match in real_glob(self, pattern):
                if "bad" in match.name:
                    raise PermissionError("denied")
                yield match

        bad = root / "20260101_bad_gpt-5-chat_it-support.jsonl"
        bad.write_text('{"x":1}\n', encoding="utf-8")
        with mock.patch.object(Path, "glob", patched_glob):
            eval_launch._wipe_prior_runs(
                "it_support_v1", "gpt-5-chat", visibility="public", owner_user_id=None
            )
        self.assertTrue(good.is_file())
        self.assertTrue(bad.is_file())


class RerunReusesScanHistoryTest(unittest.TestCase):
    """Re-running a past eval goes through the same gated /eval-run/start, so it
    reuses the model's existing safety history and never triggers a new scan.

    A model with a completed non-high-risk safety run (under ANY red-team
    profile) is approved from history; a model with no history is blocked (you
    would run safety first). This locks in "old evals reuse prior scannings".
    """

    def setUp(self) -> None:
        # /eval-run/start is @require_login — use the dev-auth bypass + a session.
        env = mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"})
        env.start()
        self.addCleanup(env.stop)
        cand = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK,
        )
        cand.start()
        self.addCleanup(cand.stop)
        self.client = create_app({"TESTING": True, "SECRET_KEY": "test"}).test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {"id": "u-test", "netid": "testuser", "display_name": "Test"}
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _history(self, tier: str) -> list[tuple[str, Path]]:
        """A completed safety run already in history, under a non-base profile."""
        p = Path(self._tmp.name) / "merged_safety_result.json"
        p.write_text(json.dumps({"status": "complete", "composite_tier": tier}),
                     encoding="utf-8")
        return [("education", p)]

    def _rerun_post(self):
        # a re-run posts the past run's params to the same launch endpoint
        return self.client.post("/eval-run/start", data={
            "candidate": "GPT 4.1 Mini", "judge": "Llama 4 Maverick",
            "suite": "it_support_v1", "max_tokens": "500",
        })

    def test_rerun_start_reuses_existing_safety_history(self) -> None:
        from frontend import pipeline
        with mock.patch.object(pipeline, "_safety_runs_from_ui_catalog",
                               return_value=[]), \
             mock.patch.object(pipeline, "_safety_result_paths",
                               return_value=self._history("medium")), \
             mock.patch.object(eval_launch, "start_run",
                               return_value=("slug1", False, "public")) as sr:
            r = self._rerun_post()
        # existing history approves the re-run — launched, no new scan triggered
        self.assertEqual(r.status_code, 302)
        sr.assert_called_once()

    def test_rerun_start_blocked_without_history(self) -> None:
        from frontend import pipeline
        with mock.patch.object(pipeline, "_safety_runs_from_ui_catalog",
                               return_value=[]), \
             mock.patch.object(pipeline, "_safety_result_paths", return_value=[]), \
             mock.patch.object(eval_launch, "start_run") as sr:
            r = self._rerun_post()
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"safety red-teaming required", r.data)
        sr.assert_not_called()

    def test_rerun_prefill_entrypoint_renders(self) -> None:
        # /eval-run/new?from=<slug> is the re-run entry point; it renders even
        # when the source run is missing (prefill just degrades to none).
        r = self.client.get("/eval-run/new?from=nonexistent-slug")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
