"""
Gateway-backed AI summaries for model detail and compare pages.

Lazy generate + disk cache keyed by rollup ``inputs_hash``. Falls back to
rules v1 when the gateway key is missing or the call fails.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from frontend import recommendation_rules

_CACHE_DIR = Path(__file__).resolve().parent / ".summary-cache"
_DEFAULT_MODEL = "GPT 4.1 Mini"


def _cache_path(slug: str, *, kind: str) -> Path:
    # Flatten the slug into a safe flat filename — an HF "org/name" identity
    # contains a "/" that would otherwise create a subdir or escape the cache
    # dir. Any rare collision self-heals via the inputs_hash guard.
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in slug)
    return _CACHE_DIR / f"{safe}.{kind}.json"


def _read_cache(slug: str, *, kind: str, inputs_hash: str) -> dict | None:
    path = _cache_path(slug, kind=kind)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("inputs_hash") != inputs_hash:
        return None
    return data


def _write_cache(slug: str, *, kind: str, inputs_hash: str, payload: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(slug, kind=kind)
    path.write_text(
        json.dumps({**payload, "inputs_hash": inputs_hash}, indent=2),
        encoding="utf-8",
    )


def _gateway_configured() -> bool:
    return bool(os.environ.get("DUKE_GATEWAY_KEY") or os.environ.get("OPENAI_API_KEY"))


def _summary_model() -> str:
    return os.environ.get("SUMMARY_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def _evidence_blob(rollup: dict) -> str:
    parts: list[str] = []
    if rollup.get("scan"):
        s = rollup["scan"]
        parts.append(f"Scan: tier={s.get('tier')}, risk_score={s.get('overall_risk_score')}")
    if rollup.get("safety"):
        s = rollup["safety"]
        parts.append(
            f"Safety: tier={s.get('tier')}, pass_rate={s.get('pass_rate')}"
        )
    if rollup.get("eval"):
        e = rollup["eval"]
        parts.append(
            f"Eval: best_overall={e.get('best_overall')}/5, suites={e.get('suites')}, "
            f"cost_usd={e.get('total_cost_usd')}, latency_ms={e.get('mean_latency_ms')}"
        )
    if rollup.get("benchmark") and rollup["benchmark"].get("kinds"):
        bits = [
            f"{k}={v.get('headline_display')}"
            for k, v in rollup["benchmark"]["kinds"].items()
        ]
        parts.append("Benchmarks: " + ", ".join(bits))
    subscores = rollup.get("subscores") or {}
    if subscores:
        parts.append("Normalized subscores (0-100): " + json.dumps(subscores))
    if rollup.get("aggregate") is not None:
        parts.append(f"Aggregate rank score: {rollup['aggregate']:.1f}")
    return "\n".join(parts) if parts else "No pillar data yet."


def _call_gateway(prompt: str, *, prior: str | None = None) -> str | None:
    if not _gateway_configured():
        return None
    try:
        from evaluator._gateway import gateway_client

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "You write concise, evidence-backed model summaries for Duke IT "
                    "analysts. Use only the evidence provided. 2-4 sentences plus "
                    "optional bullet tradeoffs. No hype; note gaps plainly."
                ),
            },
        ]
        if prior:
            messages.append({
                "role": "assistant",
                "content": f"Previous summary for continuity:\n{prior}",
            })
        messages.append({"role": "user", "content": prompt})
        resp = gateway_client().chat.completions.create(
            model=_summary_model(),
            messages=messages,
            temperature=0.2,
            max_tokens=400,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:
        return None


def _rules_fallback(rollup: dict) -> dict:
    rec = recommendation_rules.build_recommendation(rollup)
    return {
        "summary": rec["summary"],
        "tradeoffs": rec["tradeoffs"],
        "source": "rules_v1",
        "has_data": rec["has_data"],
    }


def _parse_ai_response(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    summary_lines: list[str] = []
    tradeoffs: list[str] = []
    for ln in lines:
        if ln.startswith(("-", "•", "*")):
            tradeoffs.append(ln.lstrip("-•* ").strip())
        elif ln.lower().startswith("tradeoff"):
            continue
        else:
            summary_lines.append(ln)
    summary = " ".join(summary_lines) if summary_lines else text
    return {
        "summary": summary,
        "tradeoffs": tradeoffs,
        "source": "ai",
        "has_data": True,
    }


def get_recommendation_summary(rollup: dict) -> dict:
    """Cached AI recommendation for one model; rules v1 fallback."""
    slug = rollup.get("slug") or "unknown"
    inputs_hash = rollup.get("inputs_hash") or model_rollup_inputs_hash(rollup)
    cached = _read_cache(slug, kind="recommendation", inputs_hash=inputs_hash)
    if cached:
        return cached

    prior_path = _cache_path(slug, kind="recommendation")
    prior_text = None
    if prior_path.is_file():
        try:
            prior_text = json.loads(prior_path.read_text()).get("summary")
        except (OSError, json.JSONDecodeError):
            prior_text = None

    if not rollup.get("scan") and not rollup.get("safety") and not rollup.get("eval") and not (
        rollup.get("benchmark") and rollup["benchmark"].get("kinds")
    ):
        return _rules_fallback(rollup)

    prompt = (
        f"Model: {rollup.get('display_name')}\n\n"
        f"Evidence:\n{_evidence_blob(rollup)}\n\n"
        "Write a short recommendation summary and bullet tradeoffs (security, "
        "efficacy, cost). Mention missing pillars if any."
    )
    ai_text = _call_gateway(prompt, prior=prior_text)
    if not ai_text:
        return _rules_fallback(rollup)

    result = _parse_ai_response(ai_text)
    _write_cache(slug, kind="recommendation", inputs_hash=inputs_hash, payload=result)
    return result


def get_compare_summary(rollups: list[dict]) -> dict:
    """Single AI blurb comparing multiple models; rules fallback per model."""
    if not rollups:
        return {"summary": "Select models to compare.", "tradeoffs": [], "source": "rules_v1"}

    slugs_sorted = ",".join(sorted(r["slug"] for r in rollups))
    inputs_hash = hashlib.sha256(
        slugs_sorted.encode() + "".join(r.get("inputs_hash", "") for r in rollups).encode()
    ).hexdigest()[:16]
    cache_slug = f"compare-{inputs_hash}"
    cached = _read_cache(cache_slug, kind="compare", inputs_hash=inputs_hash)
    if cached:
        return cached

    names = [r.get("display_name") for r in rollups]
    evidence = "\n\n".join(
        f"=== {r.get('display_name')} ===\n{_evidence_blob(r)}" for r in rollups
    )
    prompt = (
        f"Compare these models for a Duke analyst choosing between: {', '.join(names)}.\n\n"
        f"{evidence}\n\n"
        "Write 3-5 sentences on which model fits which use case, with explicit tradeoffs."
    )
    ai_text = _call_gateway(prompt)
    if not ai_text:
        bits = [_rules_fallback(r)["summary"] for r in rollups]
        return {
            "summary": " ".join(bits),
            "tradeoffs": [],
            "source": "rules_v1",
            "has_data": True,
        }
    result = _parse_ai_response(ai_text)
    _write_cache(cache_slug, kind="compare", inputs_hash=inputs_hash, payload=result)
    return result


def model_rollup_inputs_hash(rollup: dict) -> str:
    from frontend.model_rollup import rollup_inputs_hash

    return rollup_inputs_hash(rollup)
