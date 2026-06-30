"""Normalized launch config fingerprints for run deduplication."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

Pillar = Literal["scan", "safety", "eval", "benchmark"]

# Curated eval suites (must match frontend/eval_launch.SUITES keys)
_CURATED_EVAL_SUITES = frozenset(
    {
        "it_support_v1",
        "policy_qa_v1",
        "policy_qa_v1.1",
        "summarization_v1",
    }
)

# Benchmark keys (must match benchmarks/run_benchmark.BENCHMARKS)
_BENCHMARK_KEYS = frozenset(
    {
        "truthfulqa",
        "ifeval",
        "mmlu",
        "tomi",
        "consistency",
        "mbpp",
        "quality",
    }
)

_SAFETY_PROFILES_PUBLIC = frozenset({"base"})


def _stable_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def fingerprint_from_config(config: dict[str, Any]) -> str:
    """SHA-256 hex digest of normalized config dict."""
    return hashlib.sha256(_stable_json(config).encode("utf-8")).hexdigest()


def normalize_scan_config(
    *,
    hf_repo: str,
    skip_modelscan: bool = False,
    skip_fickling: bool = False,
    skip_modelaudit: bool = False,
    skip_deps: bool = False,
    skip_secrets: bool = False,
) -> dict[str, Any]:
    return {
        "pillar": "scan",
        "hf_repo": hf_repo.strip(),
        "skip_modelscan": bool(skip_modelscan),
        "skip_fickling": bool(skip_fickling),
        "skip_modelaudit": bool(skip_modelaudit),
        "skip_deps": bool(skip_deps),
        "skip_secrets": bool(skip_secrets),
    }


def normalize_safety_config(
    *,
    model: str,
    redteam_profile: str = "base",
    skip_policy: bool = False,
    skip_redteam: bool = False,
    skip_garak: bool = False,
    skip_promptfoo: bool = False,
    garak_probes: str | None = None,
) -> dict[str, Any]:
    probes = (garak_probes or "").strip()
    return {
        "pillar": "safety",
        "model": model.strip(),
        "redteam_profile": redteam_profile.strip(),
        "skip_policy": bool(skip_policy),
        "skip_redteam": bool(skip_redteam),
        "skip_garak": bool(skip_garak),
        "skip_promptfoo": bool(skip_promptfoo),
        "garak_probes": probes,
    }


def normalize_eval_config(
    *,
    candidate: str,
    judge: str,
    suite_key: str,
    max_tokens: int,
) -> dict[str, Any]:
    return {
        "pillar": "eval",
        "candidate": candidate.strip(),
        "judge": judge.strip(),
        "suite_key": suite_key.strip(),
        "max_tokens": int(max_tokens),
    }


def normalize_benchmark_config(
    *,
    benchmark_key: str,
    model: str,
) -> dict[str, Any]:
    return {
        "pillar": "benchmark",
        "benchmark_key": benchmark_key.strip(),
        "model": model.strip(),
    }


def normalize_config(pillar: Pillar, **kwargs: Any) -> dict[str, Any]:
    if pillar == "scan":
        return normalize_scan_config(**kwargs)
    if pillar == "safety":
        return normalize_safety_config(**kwargs)
    if pillar == "eval":
        return normalize_eval_config(**kwargs)
    if pillar == "benchmark":
        return normalize_benchmark_config(**kwargs)
    raise ValueError(f"unknown pillar: {pillar!r}")


def fingerprint(pillar: Pillar, config: dict[str, Any] | None = None, **kwargs: Any) -> str:
    cfg = config if config is not None else normalize_config(pillar, **kwargs)
    return fingerprint_from_config(cfg)


def is_public_default(pillar: Pillar, config: dict[str, Any]) -> bool:
    if pillar == "scan":
        return not any(
            config.get(k)
            for k in (
                "skip_modelscan",
                "skip_fickling",
                "skip_modelaudit",
                "skip_deps",
                "skip_secrets",
            )
        )
    if pillar == "safety":
        return (
            config.get("redteam_profile") in _SAFETY_PROFILES_PUBLIC
            and not config.get("garak_probes")
            and not config.get("skip_policy")
            and not config.get("skip_redteam")
            and not config.get("skip_garak")
            and not config.get("skip_promptfoo")
        )
    if pillar == "eval":
        suite = config.get("suite_key", "")
        return bool(suite) and suite in _CURATED_EVAL_SUITES and not str(suite).startswith("custom_")
    if pillar == "benchmark":
        return config.get("benchmark_key") in _BENCHMARK_KEYS
    return False


def resolve_visibility(
    pillar: Pillar,
    config: dict[str, Any],
    *,
    private_mode: bool,
    force_private: bool = False,
) -> str:
    """Return ``public`` or ``private`` for a launch request."""
    if force_private or not is_public_default(pillar, config):
        return "private"
    if private_mode:
        return "public"
    return "public"
