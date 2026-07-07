"""
Tests for frontend/db_fallback.py — the shared "try DB, fall back to disk"
dispatcher used by every pillar's ``get_*_data()``.

  uv run python -m unittest unit_tests.test_db_fallback -v
"""

from __future__ import annotations

import unittest

from frontend.db_fallback import get_data_with_db_fallback


class GetDataWithDbFallbackTest(unittest.TestCase):
    def test_uses_db_when_available(self) -> None:
        result = get_data_with_db_fallback(
            lambda: True, lambda: {"source": "db"}, lambda: {"source": "file"}
        )
        self.assertEqual(result, {"source": "db"})

    def test_falls_back_when_unavailable(self) -> None:
        result = get_data_with_db_fallback(
            lambda: False, lambda: {"source": "db"}, lambda: {"source": "file"}
        )
        self.assertEqual(result, {"source": "file"})

    def test_falls_back_on_db_exception(self) -> None:
        def boom() -> dict:
            raise RuntimeError("connection refused")

        result = get_data_with_db_fallback(lambda: True, boom, lambda: {"source": "file"})
        self.assertEqual(result, {"source": "file"})

    def test_falls_back_when_availability_check_raises(self) -> None:
        def boom() -> bool:
            raise RuntimeError("dsn probe failed")

        result = get_data_with_db_fallback(boom, lambda: {"source": "db"}, lambda: {"source": "file"})
        self.assertEqual(result, {"source": "file"})


if __name__ == "__main__":
    unittest.main()
