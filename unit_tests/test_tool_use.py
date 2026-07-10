"""
Tests for the tool-use / function-calling checker (execution_eval._check_tool)
and its sub-signal report (execution_eval.tool_report). No Gateway, no API.

Covers: right call, wrong tool, wrong/missing/extra args, numeric coercion,
fenced/prose-wrapped JSON, irrelevance (decline) handling, and the report math.
Also a gold-achievability pass over the real suite (every gold call passes).

Run from repo root:
  uv run python -m unittest unit_tests.test_tool_use -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import execution_eval as ee  # noqa: E402


def _task(name, args=None):
    exp = {"name": name} if name is None else {"name": name, "arguments": args or {}}
    return {"expected": exp}


_VPN = _task("check_vpn_status", {"netid": "ar455"})


class CheckToolTest(unittest.TestCase):
    def _ok(self, resp, task):
        return ee._check_tool(resp, task)[0]

    def test_correct_call(self) -> None:
        self.assertTrue(self._ok('{"name":"check_vpn_status","arguments":{"netid":"ar455"}}', _VPN))

    def test_wrong_tool(self) -> None:
        self.assertFalse(self._ok('{"name":"reset_netid_password","arguments":{"netid":"ar455"}}', _VPN))

    def test_wrong_argument_value(self) -> None:
        self.assertFalse(self._ok('{"name":"check_vpn_status","arguments":{"netid":"AR-455"}}', _VPN))

    def test_missing_argument(self) -> None:
        self.assertFalse(self._ok('{"name":"check_vpn_status","arguments":{}}', _VPN))

    def test_extra_argument_is_lenient(self) -> None:
        self.assertTrue(self._ok(
            '{"name":"check_vpn_status","arguments":{"netid":"ar455","note":"x"}}', _VPN))

    def test_fenced_and_prose_wrapped(self) -> None:
        self.assertTrue(self._ok(
            '```json\n{"name":"check_vpn_status","arguments":{"netid":"ar455"}}\n```', _VPN))
        self.assertTrue(self._ok(
            'Here: {"name":"check_vpn_status","arguments":{"netid":"ar455"}}', _VPN))

    def test_numeric_argument_coercion(self) -> None:
        task = _task("book_study_room", {"hours": 2, "room": "218"})
        # model emits the int as a string, and the room number as an int
        self.assertTrue(self._ok(
            '{"name":"book_study_room","arguments":{"hours":"2","room":218}}', task))

    def test_irrelevance_decline_json(self) -> None:
        self.assertTrue(self._ok('{"name": null}', _task(None)))

    def test_irrelevance_decline_prose(self) -> None:
        # a plain refusal (no JSON) counts as "did not call a tool"
        self.assertTrue(self._ok("I can't help with that request.", _task(None)))

    def test_irrelevance_but_called_a_tool(self) -> None:
        self.assertFalse(self._ok('{"name":"create_ticket","arguments":{}}', _task(None)))

    def test_non_irrelevance_prose_fails(self) -> None:
        self.assertFalse(self._ok("Sure, I'll check the VPN for you.", _VPN))


class ToolReportTest(unittest.TestCase):
    def test_subsignals(self) -> None:
        suite = {
            "t1": _task("check_vpn_status", {"netid": "ar455"}),
            "t2": _task("book_study_room", {"hours": 2}),
            "t3": _task(None),
        }
        rows = [
            {"question_id": "t1",  # correct
             "candidate_response": '{"name":"check_vpn_status","arguments":{"netid":"ar455"}}'},
            {"question_id": "t2",  # right tool, wrong arg
             "candidate_response": '{"name":"book_study_room","arguments":{"hours":9}}'},
            {"question_id": "t3",  # correctly declines
             "candidate_response": '{"name": null}'},
        ]
        rep = ee.tool_report(rows, suite)
        self.assertEqual((rep["n"], rep["passed"]), (3, 2))
        self.assertEqual(rep["tool_selection_accuracy"], 1.0)   # both tools picked right
        self.assertEqual(rep["argument_accuracy"], 0.5)         # 1 of 2 args right
        self.assertEqual(rep["irrelevance_accuracy"], 1.0)
        self.assertEqual((rep["n_selection"], rep["n_irrelevance"]), (2, 1))


class GoldAchievableTest(unittest.TestCase):
    def test_every_gold_call_passes_its_checker(self) -> None:
        suite = ee.load_suite("tool_use_duke_v1")
        self.assertEqual(len(suite), 15)
        for qid, task in suite.items():
            with self.subTest(question=qid):
                ok, err = ee._check_tool(json.dumps(task["expected"]), task)
                self.assertTrue(ok, f"{qid} gold fails its own checker: {err}")


if __name__ == "__main__":
    unittest.main()
