"""
Tests for frontend/db_fallback.py — the shared "try DB, fall back to disk"
dispatcher used by every pillar's ``get_*_data()``.

  uv run python -m unittest unit_tests.test_db_fallback -v
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from frontend.db_fallback import get_data_with_db_fallback, last_db_fallback_error


class GetDataWithDbFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        import frontend.db_fallback as mod

        mod._LAST_DB_ERROR = None

    def test_uses_db_when_available(self) -> None:
        result = get_data_with_db_fallback(
            lambda: True, lambda: {"source": "db"}, lambda: {"source": "file"}
        )
        self.assertEqual(result, {"source": "db"})
        self.assertIsNone(last_db_fallback_error())

    def test_falls_back_when_unavailable(self) -> None:
        result = get_data_with_db_fallback(
            lambda: False, lambda: {"source": "db"}, lambda: {"source": "file"}
        )
        self.assertEqual(result, {"source": "file"})

    def test_falls_back_on_db_exception(self) -> None:
        def boom() -> dict:
            raise RuntimeError("connection refused")

        with self.assertLogs("frontend.db_fallback", level="WARNING") as logs:
            result = get_data_with_db_fallback(
                lambda: True, boom, lambda: {"source": "file"}, pillar="scan"
            )
        self.assertEqual(result, {"source": "file"})
        self.assertIn("connection refused", last_db_fallback_error() or "")
        self.assertTrue(any("scan" in m for m in logs.output))

    def test_strict_mode_reraises_db_exception(self) -> None:
        def boom() -> dict:
            raise RuntimeError("connection refused")

        with patch.dict(os.environ, {"FRONTEND_DB_STRICT": "1"}):
            with self.assertRaises(RuntimeError):
                get_data_with_db_fallback(lambda: True, boom, lambda: {"source": "file"})

    def test_falls_back_when_availability_check_raises(self) -> None:
        def boom() -> bool:
            raise RuntimeError("dsn probe failed")

        with self.assertLogs("frontend.db_fallback", level="WARNING"):
            result = get_data_with_db_fallback(
                boom, lambda: {"source": "db"}, lambda: {"source": "file"}, pillar="eval"
            )
        self.assertEqual(result, {"source": "file"})


if __name__ == "__main__":
    unittest.main()
