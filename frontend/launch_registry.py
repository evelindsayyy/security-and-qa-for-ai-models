"""
Shared in-flight-combo liveness check used by every pillar's ``start_run()``.

Each launcher keeps its own ``_RUNNING``/``_INFLIGHT``/``_LOCK`` module
globals — the key shape genuinely differs per pillar (a slug, a
``slug/profile`` pair, an opaque parameter tuple) so the registries
themselves stay separate. What's identical everywhere is the liveness
check: is the combo's recorded job key still backed by a live process?

Overview /jobs also discovers jobs via on-disk run locks so counts survive
Flask / web-container restarts while docker pillar jobs keep running.
"""

from __future__ import annotations

import subprocess
from typing import Any, Hashable


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


def list_inflight_jobs() -> list[dict[str, Any]]:
    """All currently running pillar jobs (memory + durable lock discovery)."""
    jobs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add(
        *,
        pillar: str,
        slug: str,
        label: str,
        url: str,
        detail: str = "",
        profile: str | None = None,
    ) -> None:
        key = (pillar, f"{slug}/{profile}" if profile else slug)
        if key in seen:
            return
        seen.add(key)
        jobs.append(
            {
                "pillar": pillar,
                "slug": slug,
                "profile": profile,
                "label": label,
                "detail": detail,
                "url": url,
            }
        )

    try:
        from frontend.scan_launch import inflight_scan_slugs

        for slug in sorted(inflight_scan_slugs()):
            _add(
                pillar="scan",
                slug=slug,
                label=f"Scan · {slug}",
                detail="HF artifact scan",
                url=f"/scans/{slug}?status=running",
            )
    except Exception:
        pass

    try:
        from frontend.safety_launch import inflight_safety_keys

        for key in sorted(inflight_safety_keys()):
            if "/" not in key:
                continue
            slug, profile = key.split("/", 1)
            _add(
                pillar="safety",
                slug=slug,
                profile=profile,
                label=f"Safety · {slug}",
                detail=f"profile {profile}",
                url=f"/safety/{slug}/{profile}?status=running",
            )
    except Exception:
        pass

    try:
        from frontend.eval_launch import inflight_eval_slugs

        for slug in sorted(inflight_eval_slugs()):
            _add(
                pillar="eval",
                slug=slug,
                label=f"Eval · {slug}",
                detail="LLM-as-judge suite",
                url=f"/eval-run/{slug}?status=running",
            )
    except Exception:
        pass

    try:
        from frontend.benchmark_launch import inflight_benchmark_slugs

        for slug in sorted(inflight_benchmark_slugs()):
            _add(
                pillar="benchmark",
                slug=slug,
                label=f"Benchmark · {slug}",
                detail="Public benchmark run",
                url=f"/benchmarks/{slug}?status=running",
            )
    except Exception:
        pass

    jobs.sort(key=lambda j: (j["pillar"], j["slug"]))
    return jobs


def count_inflight() -> int:
    """Count pillar jobs that are still in flight (including after restart)."""
    return len(list_inflight_jobs())
