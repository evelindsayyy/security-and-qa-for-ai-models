"""Tests for shared dbutils helpers (no Postgres)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dbutils.env import REPO_ROOT, resolve_dsn
from dbutils.files import exclude_substrings, iter_files, read_json, read_jsonl
from dbutils.ingest import jsonb_param
from dbutils.stats import percentile


class PercentileTest(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(percentile([], 50), 0.0)

    def test_single_value(self) -> None:
        self.assertEqual(percentile([100], 95), 100.0)

    def test_p50_two_values(self) -> None:
        self.assertEqual(percentile([100, 200], 50), 150.0)


class FilesTest(unittest.TestCase):
    def test_read_jsonl_skips_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.jsonl"
            path.write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf-8")
            rows = read_jsonl(path)
            assert rows is not None
            self.assertEqual(len(rows), 2)

    def test_read_jsonl_none_on_bad_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_text("not json", encoding="utf-8")
            self.assertIsNone(read_jsonl(path))

    def test_read_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            path.write_text('{"model_id": "gpt2"}', encoding="utf-8")
            data = read_json(path)
            assert data is not None
            self.assertEqual(data["model_id"], "gpt2")

    def test_iter_files_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.json").write_text("{}", encoding="utf-8")
            (root / "a.json").write_text("{}", encoding="utf-8")
            names = [p.name for p in iter_files(root, "*.json")]
            self.assertEqual(names, ["a.json", "b.json"])

    def test_exclude_substrings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scan_result.json").write_text("{}", encoding="utf-8")
            (root / "scan_result.trace.json").write_text("{}", encoding="utf-8")
            paths = iter_files(
                root,
                "*.json",
                exclude_if=exclude_substrings(".trace"),
            )
            self.assertEqual([p.name for p in paths], ["scan_result.json"])


class JsonbParamTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = {"scores": {"accuracy": {"score": 5}}, "schema_version": "1.0.0"}
        self.assertEqual(json.loads(jsonb_param(payload)), payload)


class ResolveDsnTest(unittest.TestCase):
    def test_first_key_wins(self) -> None:
        with mock.patch.dict(os.environ, {"A_DSN": "a", "B_DSN": "b"}, clear=False):
            self.assertEqual(resolve_dsn("A_DSN", "B_DSN"), "a")

    def test_fallback_database_url(self) -> None:
        with mock.patch.dict(os.environ, {"DATABASE_URL": "fallback"}, clear=True):
            self.assertEqual(resolve_dsn("MISSING"), "fallback")


class RepoRootTest(unittest.TestCase):
    def test_points_at_repo(self) -> None:
        self.assertTrue((REPO_ROOT / "pyproject.toml").is_file())


if __name__ == "__main__":
    unittest.main()
