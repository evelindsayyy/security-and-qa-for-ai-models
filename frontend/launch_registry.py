"""
Shared in-flight-combo liveness check used by every pillar's ``start_run()``.

Each launcher keeps its own ``_RUNNING``/``_INFLIGHT``/``_LOCK`` module
globals — the key shape genuinely differs per pillar (a slug, a
``slug/profile`` pair, an opaque parameter tuple) so the registries
themselves stay separate. What's identical everywhere is the liveness
check: is the combo's recorded job key still backed by a live process?
"""

from __future__ import annotations

import subprocess
from typing import Hashable


def check_inflight_combo(
    running: dict[str, subprocess.Popen],
    inflight: dict[Hashable, str],
    combo: Hashable,
) -> str | None:
    """Return the existing job key if ``combo`` is already in flight and its
    process is still alive, else ``None``."""
    existing = inflight.get(combo)
    if existing and running.get(existing) is not None and running[existing].poll() is None:
        return existing
    return None


def count_inflight() -> int:
    """Count pillar jobs whose subprocess is still alive."""
    total = 0
    for mod_name in (
        "frontend.scan_launch",
        "frontend.safety_launch",
        "frontend.eval_launch",
        "frontend.benchmark_launch",
    ):
        try:
            mod = __import__(mod_name, fromlist=["_RUNNING"])
            running = getattr(mod, "_RUNNING", {})
            for proc in running.values():
                if proc is not None and proc.poll() is None:
                    total += 1
        except Exception:
            continue
    return total
