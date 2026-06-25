"""
End-to-end pipeline test: runs the REAL runner.main() against a stubbed
Gateway client — no API calls, no cost. One run mixes every failure mode
the pipeline must survive:

  q1 healthy candidate            -> OK row with judged scores + overall
  q2 empty candidate response     -> candidate_failed row, judge NOT called
  q3 candidate API error          -> candidate_failed row, judge NOT called
  q4 malformed suite line         -> fallback row from the defensive catch-all

The hard rule under test (evaluator/CLAUDE.md): the runner never crashes,
and every question produces exactly one JSONL row.

Run from repo root:
  uv run python -m unittest unit_tests.test_runner_pipeline -v
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import candidate  # noqa: E402
import judge  # noqa: E402
import runner  # noqa: E402


RUBRIC_YAML = """\
rubric_version: smoke_v1
dimensions:
  accuracy:
    scale: [1, 5]
    weight: 0.7
  tone:
    scale: [1, 3]
    weight: 0.3
aggregation:
  display_scale: 5
"""

# Minimal template with every placeholder judge_response formats, including
# {output_schema} so the runner's fail-fast prompt/rubric check passes.
JUDGE_PROMPT = """\
Q: {question}
REF: {reference}
CAND: {candidate}
RUBRIC: {rubric_yaml}
OUTPUT: {output_schema}
"""

JUDGE_JSON = json.dumps({
    "accuracy": {"score": 4, "rationale": "mostly right"},
    "tone": {"score": 3, "rationale": "clear"},
})


def _response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20),
    )


class _CandidateStub:
    """Routes by markers in the question text; counts judge-visible calls."""

    def __init__(self) -> None:
        self.calls = 0
        self.with_options = lambda **kw: self
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls += 1
        question = kwargs["messages"][1]["content"]
        if "EMPTY" in question:
            return _response("")  # reasoning-budget artifact
        if "APIERR" in question:
            raise RuntimeError("gateway exploded")
        return _response("a perfectly good answer")


class _JudgeStub:
    def __init__(self) -> None:
        self.calls = 0
        self.last_kwargs: dict = {}
        self.with_options = lambda **kw: self
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return _response(JUDGE_JSON)


class RunnerPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

        (self.dir / "suite.jsonl").write_text(
            json.dumps({"task_suite_version": "smoke_v1"}) + "\n"
            + json.dumps({"id": "q1", "question": "GOOD one", "reference": "ref1"}) + "\n"
            + json.dumps({"id": "q2", "question": "EMPTY one", "reference": "ref2"}) + "\n"
            + json.dumps({"id": "q3", "question": "APIERR one", "reference": "ref3"}) + "\n"
            + json.dumps({"id": "q4", "reference": "missing question key"}) + "\n",
            encoding="utf-8",
        )
        (self.dir / "rubric.yaml").write_text(RUBRIC_YAML, encoding="utf-8")
        (self.dir / "system.txt").write_text("be helpful", encoding="utf-8")
        (self.dir / "judge_prompt.txt").write_text(JUDGE_PROMPT, encoding="utf-8")

        self.cand_stub = _CandidateStub()
        self.judge_stub = _JudgeStub()
        # Stored so a test can re-run with extra flags (e.g. the DCC provenance
        # flags) by patching sys.argv to self.base_argv + [...] inside the test.
        self.base_argv = [
            "runner.py",
            "--candidate-model", "stub-model",
            "--judge-model", "stub-judge",
            "--suite", str(self.dir / "suite.jsonl"),
            "--rubric", str(self.dir / "rubric.yaml"),
            "--system-prompt", str(self.dir / "system.txt"),
            "--judge-prompt", str(self.dir / "judge_prompt.txt"),
            "--output-dir", str(self.dir / "results"),
            "--judge-max-tokens", "1234",
        ]
        for patcher in (
            mock.patch.object(candidate, "gateway_client", return_value=self.cand_stub),
            mock.patch.object(judge, "gateway_client", return_value=self.judge_stub),
            mock.patch.object(candidate, "_CACHE_DIR", self.dir / "cache_c"),
            mock.patch.object(judge, "_CACHE_DIR", self.dir / "cache_j"),
            mock.patch.object(sys, "argv", self.base_argv),
            # Isolate from the real DB: stub the post-run auto-ingest so unit
            # tests never touch Postgres (robust regardless of env / CI).
            mock.patch("dbutils.post_run.maybe_sync_artifact"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _run(self) -> dict[str, dict]:
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            exit_code = runner.main()
        self.assertEqual(exit_code, 0)
        results = [p for p in (self.dir / "results").glob("*.jsonl")
                   if "_trace" not in p.name]
        self.assertEqual(len(results), 1)
        rows = [json.loads(line) for line in results[0].read_text().splitlines()]
        return {r["question_id"]: r for r in rows}

    def test_one_row_per_question_no_crash(self) -> None:
        rows = self._run()
        self.assertEqual(set(rows), {"q1", "q2", "q3", "q4"})

    def test_healthy_question_gets_judged_scores(self) -> None:
        rows = self._run()
        q1 = rows["q1"]
        self.assertFalse(q1["candidate_failed"])
        self.assertFalse(q1["judge_failed"])
        self.assertEqual(q1["scores"]["accuracy"]["score"], 4)
        # 0.7*(4/5) + 0.3*(3/3) = 0.86 -> 4.3 on the 0-5 display scale
        self.assertEqual(q1["overall"], 4.3)
        self.assertEqual(q1["suite"], "smoke")
        self.assertEqual(q1["adaptation"]["task_suite_version"], "smoke_v1")

    def test_empty_response_fails_candidate_and_skips_judge(self) -> None:
        rows = self._run()
        q2 = rows["q2"]
        self.assertTrue(q2["candidate_failed"])
        self.assertIn("empty response", q2["error"])
        self.assertIsNone(q2["overall"])
        # judge called exactly once across the whole run (only for q1)
        self.assertEqual(self.judge_stub.calls, 1)

    def test_api_error_fails_candidate_without_crashing(self) -> None:
        rows = self._run()
        q3 = rows["q3"]
        self.assertTrue(q3["candidate_failed"])
        self.assertIn("gateway exploded", q3["error"])

    def test_malformed_suite_line_gets_fallback_row(self) -> None:
        rows = self._run()
        q4 = rows["q4"]
        self.assertTrue(q4["candidate_failed"])
        self.assertIn("runner exception", q4["error"])
        self.assertEqual(q4["schema_version"], rows["q1"]["schema_version"])

    def test_judge_max_tokens_flag_reaches_the_judge_call(self) -> None:
        # Reasoning judges (gpt-oss-120b) get truncated at the old fixed 600;
        # the flag must flow through runner -> judge_response -> API call.
        self._run()
        self.assertEqual(self.judge_stub.last_kwargs.get("max_tokens"), 1234)

    def test_empty_response_not_cached_but_good_one_is(self) -> None:
        self._run()
        cached = list((self.dir / "cache_c").glob("*.json"))
        self.assertEqual(len(cached), 1)  # only q1's healthy answer
        data = json.loads(cached[0].read_text())
        self.assertEqual(data["response"], "a perfectly good answer")

    def test_default_provenance_is_gateway(self) -> None:
        # No --inference-backend / --hf-repo: the additive 1.1.0 fields take
        # their defaults, so a normal Gateway run is labeled as such.
        rows = self._run()
        adapt = rows["q1"]["adaptation"]
        self.assertEqual(adapt["inference_backend"], "gateway")
        self.assertIsNone(adapt["hf_repo"])

    def test_provenance_flags_land_in_every_row(self) -> None:
        # The DCC open-weight eval passes these; they must reach Adaptation on
        # EVERY row (healthy + failure rows alike) so the whole run is tagged.
        # (We omit --candidate-endpoint on purpose: it would bypass the stub and
        # hit a real socket; provenance is independent of endpoint routing.)
        dcc_argv = self.base_argv + [
            "--inference-backend", "dcc",
            "--hf-repo", "Qwen/Qwen2.5-7B-Instruct",
        ]
        with mock.patch.object(sys, "argv", dcc_argv):
            rows = self._run()
        for qid, r in rows.items():
            self.assertEqual(r["adaptation"]["inference_backend"], "dcc", qid)
            self.assertEqual(
                r["adaptation"]["hf_repo"], "Qwen/Qwen2.5-7B-Instruct", qid)


class RunnerSkipJudgeTest(unittest.TestCase):
    """Execution-scored suites: candidate-only run, judge auto-skipped.

    The suite's metadata declares ``scoring: execution`` — so the runner skips
    the judge WITHOUT a --skip-judge flag and WITHOUT a --judge-model. No rubric,
    no 'reference' field; rows carry empty scores (functional scoring happens
    out-of-band in execution_eval).
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        # scoring=execution in the metadata is what routes the runner here.
        (self.dir / "sql.jsonl").write_text(
            json.dumps({"task_suite_version": "sql_smoke_v1", "scoring": "execution"}) + "\n"
            + json.dumps({"id": "s1", "question": "count the rows",
                          "setup": "CREATE TABLE t(n INTEGER)", "expected": [[0]]}) + "\n"
            + json.dumps({"id": "s2", "question": "count again",
                          "setup": "CREATE TABLE t(n INTEGER)", "expected": [[0]]}) + "\n",
            encoding="utf-8",
        )
        (self.dir / "system.txt").write_text("write SQL", encoding="utf-8")

        self.cand_stub = _CandidateStub()
        self.judge_stub = _JudgeStub()
        self.argv = [
            "runner.py",
            "--candidate-model", "stub-model",
            "--suite", str(self.dir / "sql.jsonl"),
            "--system-prompt", str(self.dir / "system.txt"),
            "--output-dir", str(self.dir / "results"),
            # NO --skip-judge, NO --judge-model: the suite's scoring field drives it.
        ]
        for patcher in (
            mock.patch.object(candidate, "gateway_client", return_value=self.cand_stub),
            mock.patch.object(judge, "gateway_client", return_value=self.judge_stub),
            mock.patch.object(candidate, "_CACHE_DIR", self.dir / "cache_c"),
            mock.patch.object(sys, "argv", self.argv),
            mock.patch("dbutils.post_run.maybe_sync_artifact"),  # don't touch the real DB
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _rows(self) -> dict[str, dict]:
        self.assertEqual(runner.main(), 0)
        out = [p for p in (self.dir / "results").glob("*.jsonl")
               if "_trace" not in p.name]
        self.assertEqual(len(out), 1)
        return {r["question_id"]: r for r in
                (json.loads(line) for line in out[0].read_text().splitlines())}

    def test_judge_is_never_called(self) -> None:
        self._rows()
        self.assertEqual(self.judge_stub.calls, 0)

    def test_candidate_rows_written_without_scores(self) -> None:
        rows = self._rows()
        self.assertEqual(set(rows), {"s1", "s2"})
        for r in rows.values():
            self.assertFalse(r["candidate_failed"])
            self.assertFalse(r["judge_failed"])
            self.assertEqual(r["scores"], {})
            self.assertIsNone(r["overall"])
            self.assertEqual(r["candidate_response"], "a perfectly good answer")

    def test_no_judge_model_needed(self) -> None:
        rows = self._rows()
        self.assertEqual(rows["s1"]["adaptation"]["judge_model"], "(none)")

    def test_skip_judge_flag_still_overrides_a_non_execution_suite(self) -> None:
        # A suite WITHOUT scoring=execution, run with the --skip-judge override:
        # the judge is still skipped and no judge model is required.
        (self.dir / "plain.jsonl").write_text(
            json.dumps({"task_suite_version": "plain_v1"}) + "\n"
            + json.dumps({"id": "p1", "question": "hello",
                          "setup": "CREATE TABLE t(n INTEGER)", "expected": [[0]]}) + "\n",
            encoding="utf-8",
        )
        argv = ["runner.py", "--candidate-model", "stub-model",
                "--suite", str(self.dir / "plain.jsonl"),
                "--system-prompt", str(self.dir / "system.txt"),
                "--output-dir", str(self.dir / "results2"), "--skip-judge"]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(runner.main(), 0)
        self.assertEqual(self.judge_stub.calls, 0)


if __name__ == "__main__":
    unittest.main()
