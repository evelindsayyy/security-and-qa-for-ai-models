"""Garak report completeness validation and related pipeline guards."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from safety.garak import run_garak
from safety.garak.report_validation import (
    expected_module_count,
    validate_report,
)
from safety.run import garak_xdg_env

DUKE14_PROBE_SPEC = (
    "packagehallucination,snowball,encoding,goodside,web_injection,sysprompt_extraction,"
    "apikey,promptinject,dan.Dan_11_0,dan.DanInTheWild,misleading,leakreplay,latentinjection,"
    "divergence"
)


def _write_report(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


class ExpectedModuleCountTest(unittest.TestCase):
    def test_duke14_has_thirteen_unique_modules(self) -> None:
        self.assertEqual(expected_module_count(DUKE14_PROBE_SPEC), 13)


class ValidateReportTest(unittest.TestCase):
    def test_rejects_report_without_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "garak-duke.report.jsonl"
            rows = [
                {"entry_type": "init", "garak_version": "0.15.1"},
                {"entry_type": "eval", "probe": "encoding.InjectHex", "passed": 1, "fails": 0},
                {"entry_type": "eval", "probe": "dan.Dan_11_0", "passed": 1, "fails": 0},
            ]
            _write_report(report, rows)
            ok, err, analysis = validate_report(report, probe_spec=DUKE14_PROBE_SPEC)
            self.assertFalse(ok)
            self.assertIn("no completion entry", err)
            self.assertEqual(analysis["completed_module_count"], 2)

    def test_accepts_complete_report_with_all_modules(self) -> None:
        modules = [
            "packagehallucination", "snowball", "encoding", "goodside", "web_injection",
            "sysprompt_extraction", "apikey", "promptinject", "dan", "misleading",
            "leakreplay", "latentinjection", "divergence",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "garak-duke.report.jsonl"
            rows: list[dict] = [{"entry_type": "init"}]
            for module in modules:
                rows.append({"entry_type": "eval", "probe": f"{module}.Example"})
            rows.append({"entry_type": "completion"})
            _write_report(report, rows)
            ok, err, analysis = validate_report(report, probe_spec=DUKE14_PROBE_SPEC)
            self.assertTrue(ok)
            self.assertEqual(err, "")
            self.assertEqual(analysis["completed_module_count"], 13)


class GarakXdgEnvTest(unittest.TestCase):
    def test_sets_user_and_logname_for_container(self) -> None:
        env = garak_xdg_env("garak-env-test")
        self.assertEqual(env["USER"], "garak")
        self.assertEqual(env["LOGNAME"], "garak")
        self.assertIn("garak-env-test", env["HOME"])


class ToxicDetectorPreflightTest(unittest.TestCase):
    def test_prefetch_toxic_detector_exits_on_failure(self) -> None:
        with mock.patch(
            "garak.detectors.unsafe_content.ToxicCommentModel",
            side_effect=KeyError("getpwuid(): uid not found"),
        ):
            with self.assertRaises(SystemExit) as ctx:
                run_garak._prefetch_toxic_detector()
            self.assertEqual(ctx.exception.code, 1)

    def test_prefetch_toxic_detector_succeeds(self) -> None:
        with mock.patch("garak.detectors.unsafe_content.ToxicCommentModel") as model_cls:
            run_garak._prefetch_toxic_detector()
            model_cls.assert_called_once()


class ExitStatusTest(unittest.TestCase):
    def test_exit_status_fails_on_incomplete_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "garak-duke.report.jsonl"
            _write_report(
                report,
                [{"entry_type": "eval", "probe": "encoding.InjectHex", "passed": 1, "fails": 0}],
            )
            rc = run_garak._exit_status(tmp, 0, DUKE14_PROBE_SPEC)
            self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
