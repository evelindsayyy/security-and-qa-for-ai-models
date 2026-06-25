"""Collect per-run API timing and token usage for benchmark summaries."""

from __future__ import annotations

import json
import statistics
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_active: "RunStatsCollector | None" = None


class RunStatsCollector:
    """Accumulates latency and token usage across API calls in one benchmark run."""

    def __init__(self) -> None:
        self._latencies_ms: list[float] = []
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.api_calls = 0
        self.api_calls_failed = 0

    def record_success(self, latency_ms: float, usage: dict[str, int] | None) -> None:
        self.api_calls += 1
        self._latencies_ms.append(latency_ms)
        if usage:
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)

    def record_failure(self, latency_ms: float | None = None) -> None:
        self.api_calls_failed += 1
        if latency_ms is not None:
            self._latencies_ms.append(latency_ms)

    def _latency_summary(self) -> dict[str, float | None]:
        if not self._latencies_ms:
            return {"mean": None, "p50": None, "p95": None}
        sorted_ms = sorted(self._latencies_ms)
        n = len(sorted_ms)

        def _pct(p: float) -> float:
            idx = min(n - 1, max(0, int(p * n) - 1))
            return round(sorted_ms[idx], 1)

        return {
            "mean": round(statistics.mean(sorted_ms), 1),
            "p50": _pct(0.50),
            "p95": _pct(0.95),
        }

    def to_dict(self) -> dict[str, Any]:
        tokens: dict[str, int | None] = {
            "prompt": self.prompt_tokens or None,
            "completion": self.completion_tokens or None,
            "total": self.total_tokens or None,
        }
        if not any(tokens.values()):
            tokens = {"prompt": None, "completion": None, "total": None}
        return {
            "api_calls": self.api_calls,
            "api_calls_failed": self.api_calls_failed,
            "latency_ms": self._latency_summary(),
            "tokens": tokens,
        }


def get_active_run_stats() -> RunStatsCollector | None:
    return _active


@contextmanager
def run_with_stats() -> Iterator[RunStatsCollector]:
    """Activate a :class:`RunStatsCollector` for the duration of a benchmark run."""
    global _active
    collector = RunStatsCollector()
    _active = collector
    try:
        yield collector
    finally:
        _active = None


def attach_run_stats(block: dict[str, Any]) -> dict[str, Any]:
    """Merge active collector stats into a summary/metrics dict (in place)."""
    collector = get_active_run_stats()
    if collector is not None:
        block["run_stats"] = collector.to_dict()
    return block


def write_stats_sidecar(path: str | Path | None = None) -> None:
    """Persist stats to ``BENCHMARK_STATS_PATH`` or an explicit *path*."""
    collector = get_active_run_stats()
    if collector is None:
        return
    dest = path or __import__("os").environ.get("BENCHMARK_STATS_PATH")
    if not dest:
        return
    p = Path(dest)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(collector.to_dict(), indent=2), encoding="utf-8")


def load_stats_sidecar(path: Path) -> dict[str, Any]:
    sidecar = path.parent / f"{path.stem}.stats.json"
    if not sidecar.is_file():
        return {}
    try:
        return json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def merge_wall_time(block: dict[str, Any], wall_sec: float) -> None:
    rs = block.setdefault("run_stats", {})
    rs["wall_time_sec"] = round(wall_sec, 2)
