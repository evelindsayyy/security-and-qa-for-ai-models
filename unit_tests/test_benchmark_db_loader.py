"""
Tests for benchmarks/db/load_benchmarks.py — pure transforms only, no database.

Run from repo root:
  uv run python -m unittest unit_tests.test_benchmark_db_loader -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from benchmarks.db.load_benchmarks import load_file, load_into
from benchmarks.db.transforms import benchmark_run_row, detect_kind


class DetectKindTest(unittest.TestCase):
    def test_truthfulqa_fixture(self) -> None:
        path = _REPO / "unit_tests" / "fixtures" / "benchmark_truthfulqa.json"
        self.assertEqual(detect_kind(path), "truthfulqa")

    def test_ifeval_fixture(self) -> None:
        path = _REPO / "unit_tests" / "fixtures" / "benchmark_ifeval.jsonl"
        self.assertEqual(detect_kind(path), "ifeval")


class BenchmarkRunRowTest(unittest.TestCase):
    def test_truthfulqa_maps_fields(self) -> None:
        path = _REPO / "unit_tests" / "fixtures" / "benchmark_truthfulqa.json"
        row = benchmark_run_row(path)
        assert row is not None
        self.assertEqual(row["benchmark_key"], "truthfulqa")
        self.assertEqual(row["gateway_model_id"], "gpt-5-chat")
        self.assertEqual(row["headline_metric"], "accuracy")
        self.assertAlmostEqual(row["headline_value"], 0.75)
        self.assertEqual(row["n_items"], 4)
        self.assertEqual(len(row["items"]), 2)
        self.assertEqual(row["completed_at"], "20260618T120000+00:00")

    def test_ifeval_maps_fields(self) -> None:
        path = _REPO / "unit_tests" / "fixtures" / "benchmark_ifeval.jsonl"
        row = benchmark_run_row(path)
        assert row is not None
        self.assertEqual(row["benchmark_key"], "ifeval")
        self.assertEqual(row["gateway_model_id"], "GPT 4.1 Mini")
        self.assertEqual(row["headline_metric"], "pass_rate")
        self.assertAlmostEqual(row["headline_value"], 0.5)
        self.assertEqual(row["n_items"], 2)


class LoadFileTest(unittest.TestCase):
    def test_load_file_from_temp_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = json.loads(
                (_REPO / "unit_tests" / "fixtures" / "benchmark_truthfulqa.json").read_text()
            )
            path = root / "20260618T120000Z_truthfulqa_gpt-5-chat.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            row = load_file(path)
            assert row is not None
            self.assertEqual(row["output_slug"], path.stem)


class FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple] = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql.strip(), params))

    def fetchone(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class LoadIntoTest(unittest.TestCase):
    def test_inserts_one_row(self) -> None:
        path = _REPO / "unit_tests" / "fixtures" / "benchmark_truthfulqa.json"
        row = load_file(path)
        assert row is not None
        conn = FakeConn()
        load_into(conn, [row])
        self.assertTrue(conn.committed)
        self.assertEqual(len(conn.cursor_obj.executed), 1)
        _sql, params = conn.cursor_obj.executed[0]
        self.assertEqual(params["output_slug"], path.stem)
        self.assertIn("ON CONFLICT", _sql)


if __name__ == "__main__":
    unittest.main()
