"""
Tests for the live "Start run" flow — no subprocess spawn, no API calls.

The security-critical path is allowlist validation in eval_launch +
the 400 behavior of POST /eval-run/start: nothing outside the allowlist
may ever reach subprocess.Popen.

Run from repo root:
  uv run python -m unittest unit_tests.test_eval_launch -v
"""

from __future__ import annotations

import re
import unittest
from unittest import mock

from frontend import create_app
from frontend import eval_launch


class ValidateLaunchTest(unittest.TestCase):
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
                "candidate": "GPT 4.1 Mini", "judge": "Llama 3.3",
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
            "candidate": "gpt-5.1-chat", "judge": "Llama 3.3",
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


if __name__ == "__main__":
    unittest.main()
