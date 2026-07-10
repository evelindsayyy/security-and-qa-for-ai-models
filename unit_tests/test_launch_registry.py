"""
Tests for frontend/launch_registry.py — the shared in-flight-combo liveness
check used by every pillar's ``start_run()``.

  uv run python -m unittest unit_tests.test_launch_registry -v
"""

from __future__ import annotations

import unittest

from frontend.launch_registry import check_inflight_combo


class _FakeProc:
    def __init__(self, alive: bool) -> None:
        self._alive = alive

    def poll(self):
        return None if self._alive else 0


class CheckInflightComboTest(unittest.TestCase):
    def test_returns_key_when_process_alive(self) -> None:
        running = {"job-1": _FakeProc(alive=True)}
        inflight = {("a", "b"): "job-1"}
        self.assertEqual(check_inflight_combo(running, inflight, ("a", "b")), "job-1")

    def test_returns_none_when_combo_not_tracked(self) -> None:
        self.assertIsNone(check_inflight_combo({}, {}, ("a", "b")))

    def test_returns_none_when_process_has_exited(self) -> None:
        running = {"job-1": _FakeProc(alive=False)}
        inflight = {("a", "b"): "job-1"}
        self.assertIsNone(check_inflight_combo(running, inflight, ("a", "b")))

    def test_returns_none_when_process_missing_from_registry(self) -> None:
        inflight = {("a", "b"): "job-1"}
        self.assertIsNone(check_inflight_combo({}, inflight, ("a", "b")))


if __name__ == "__main__":
    unittest.main()
