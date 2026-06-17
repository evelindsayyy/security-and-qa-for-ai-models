"""
Tests for safety/exporters/garak.py report export.

  uv run python -m unittest unit_tests.test_garak_exporter -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

from safety.exporters.garak import _probe_module, export_from_garak_report

_ROOT = Path(__file__).resolve().parent.parent
_FIXTURE = _ROOT / "unit_tests/fixtures/garak_sample.report.jsonl"


class ProbeModuleTest(unittest.TestCase):
    def test_dotted_probe_rolls_up(self) -> None:
        self.assertEqual(_probe_module("dan.Dan_11_0"), "dan")
        self.assertEqual(_probe_module("encoding"), "encoding")


class ExportFromGarakReportTest(unittest.TestCase):
    def test_per_module_pass_rate(self) -> None:
        doc = export_from_garak_report(_FIXTURE, gateway_model_id="gpt-5.5")
        self.assertEqual(doc["gateway_model_id"], "gpt-5.5")
        # dan (0 fails + 2 fails) and encoding (0 fails) → 1/2 modules pass
        self.assertAlmostEqual(doc["summary_pass_rate"], 0.5, places=3)
        modules = {f["probe_id"] for f in doc["findings"]}
        self.assertEqual(modules, {"garak.dan", "garak.encoding"})

    def test_failed_module_marked_not_passed(self) -> None:
        doc = export_from_garak_report(_FIXTURE)
        dan = next(f for f in doc["findings"] if f["probe_id"] == "garak.dan")
        self.assertFalse(dan["passed"])
        self.assertEqual(dan["category"], "jailbreak")


if __name__ == "__main__":
    unittest.main()
