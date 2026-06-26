"""Tests for dbutils.run_lock."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from dbutils import run_lock


class RunLockTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.lock = Path(self._tmp.name) / "run.lock"

    def test_acquire_and_release(self) -> None:
        self.assertTrue(run_lock.try_acquire(self.lock, command="test"))
        self.assertTrue(run_lock.is_active(self.lock))
        run_lock.release(self.lock)
        self.assertFalse(run_lock.is_active(self.lock))

    def test_second_acquire_fails_while_active(self) -> None:
        self.assertTrue(run_lock.try_acquire(self.lock, pid=os.getpid(), source="cli"))
        self.assertFalse(run_lock.try_acquire(self.lock, pid=os.getpid() + 9999))
        run_lock.release(self.lock)

    def test_stale_lock_removed_when_pid_dead(self) -> None:
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text(
            '{"pid": 99999999, "started_at": "2020-01-01T00:00:00Z", "source": "cli"}',
            encoding="utf-8",
        )
        self.assertFalse(run_lock.is_active(self.lock))
        self.assertFalse(self.lock.is_file())

    def test_should_skip_cli_when_frontend_holds_lock(self) -> None:
        run_lock.try_acquire(
            self.lock,
            pid=os.getpid(),
            source=run_lock.FRONTEND_SOURCE,
        )
        self.assertTrue(run_lock.should_skip_cli_acquire(self.lock))
        run_lock.release(self.lock)

    def test_read_log_tail(self) -> None:
        from dbutils.log_tail import read_log_tail

        log = Path(self._tmp.name) / "run.log"
        log.write_text("line1\nline2\nline3\n", encoding="utf-8")
        tail = read_log_tail(log, max_bytes=100, max_lines=2)
        self.assertEqual(tail, "line2\nline3")


if __name__ == "__main__":
    unittest.main()
