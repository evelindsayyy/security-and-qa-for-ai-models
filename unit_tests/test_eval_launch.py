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
os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

import re
import unittest
from unittest import mock

from frontend import create_app
from frontend import eval_launch


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

    def test_complete_when_rows_match_suite_size(self) -> None:
        slug = "20990101T000000Z_it_support_v1_x"
        n = eval_launch.suite_question_count("it_support_v1")
        (self.dir / f"{slug}.jsonl").write_text("{}\n" * n, encoding="utf-8")
        s = eval_launch.get_status(slug)
        self.assertEqual(s["status"], "complete")
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
        # Offline + deterministic candidate allowlist (see ValidateLaunchTest).
        # Also avoids the OpenAI client's platform/uname subprocess, which
        # would otherwise inflate the patched global subprocess.Popen count.
        patcher = mock.patch.object(
            eval_launch, "candidate_models",
            return_value=eval_launch._CANDIDATE_FALLBACK,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = create_app({"TESTING": True}).test_client()

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
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None
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
        fake_proc = mock.Mock()
        fake_proc.poll.return_value = None  # still running
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
        self.client = create_app({"TESTING": True}).test_client()

    def test_invalid_questions_rejected(self) -> None:
        r = self.client.post("/eval-run/start-custom", data={
            "candidate": "gpt-5-chat", "judge": "Llama 4 Maverick",
            "max_tokens": "500", "questions": "not json",
        })
        self.assertEqual(r.status_code, 400)

    def test_valid_custom_spawns_and_redirects(self) -> None:
        fake = mock.Mock()
        fake.poll.return_value = None
        with mock.patch.object(eval_launch.subprocess, "Popen", return_value=fake):
            r = self.client.post("/eval-run/start-custom", data={
                "candidate": "gpt-5-chat", "judge": "Llama 4 Maverick",
                "max_tokens": "500",
                "questions": '{"question": "Q?", "reference": "A"}',
            })
        self.assertEqual(r.status_code, 302)
        self.assertIn("custom_", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
