"""
candidate.py

Thin wrapper over the OpenAI SDK pointed at the Duke AI Gateway (LiteLLM).
One public function: ``generate_candidate``.

Used by the runner (Wednesday) to call each candidate model on each suite
question. Captures wall-clock latency and token usage, returns a small
dataclass, and never raises on API failure: per ``evaluator/CLAUDE.md`` a
single bad call must not kill a 12-question run.

Environment is read by ``_gateway.py`` — see that module for env var names.

File cache:
    ``evaluator/cache/candidates/<sha256>.json``  keyed on
    ``(model, system_prompt, question, temperature, max_tokens)``.  Re-runs
    with the same inputs return the cached row WITHOUT calling the API. The
    cached ``latency_ms`` is the original call's wall-clock, not the
    cache-read time, so operational metrics survive across re-runs. Failed
    calls are NOT cached (transient errors get retried on re-run) — and
    that includes empty visible responses, which reasoning models produce
    when hidden thinking consumes the whole max_tokens budget; re-running
    with a bigger budget must retry, not replay the cached empty text.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from _gateway import gateway_client

_CACHE_DIR = Path(__file__).parent / "cache" / "candidates"


# Result dataclass

@dataclass
class CandidateResult:
    """What ``generate_candidate`` returns. Plain dataclass (not frozen) so
    the runner can read fields directly into ``Operational`` / ``EvaluationResult``
    in schemas.py without copy hoops.
    """

    response: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    failed: bool = False
    error: Optional[str] = None


# File cache

def _cache_key( # hash the inputs that should produce identical outputs
    *, model: str, system_prompt: str, question: str, temperature: float,
    max_tokens: int,
) -> str:
    # max_tokens is part of the key: for reasoning models the budget changes
    # the visible output (a starved budget yields empty text), so a re-run
    # with a different budget must miss the cache and call the API.
    raw = (
        f"{model}|{system_prompt}|{question}|{temperature:.4f}|{max_tokens}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_path(key: str) -> Path: # where to store/look for that hash
    return _CACHE_DIR / f"{key}.json"


def _cache_read(key: str) -> Optional[CandidateResult]: # return a CandidateResult if the file exists, else None
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return CandidateResult(**data)
    except (json.JSONDecodeError, OSError, TypeError, KeyError) as e:
        # A truncated (killed mid-write) or stale-shape entry must read as a
        # cache miss, not crash the run. Drop it; the fresh API call rewrites it.
        print(
            f"  WARN: discarding corrupt candidate cache entry {path.name}: {e}",
            file=sys.stderr,
        )
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _cache_write(key: str, result: CandidateResult) -> None: # save the results to disk as JSON
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = _cache_path(key)
    # Write-then-rename so a killed run never leaves a half-written entry.
    # The pid suffix keeps concurrent runs from sharing a temp file; the
    # rename itself is atomic on POSIX.
    tmp = target.with_name(f"{key}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(asdict(result), f, ensure_ascii=False, indent=2)
    tmp.replace(target)


# Public API

def generate_candidate(
    *,
    question: str,
    model: str,
    system_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 500,
    timeout_sec: float = 30.0,
) -> CandidateResult:
    """Send ``question`` to ``model`` via the Duke AI Gateway.

    Never raises on API failure — returns a ``CandidateResult`` with
    ``failed=True`` and the error string. The runner inspects ``failed``
    to decide whether to skip the judge step and write a failure row.

    Successful responses are cached; cache hits return the original call's
    ``latency_ms`` so operational metrics survive re-runs.
    """
    key = _cache_key( # Compute the cache key from the inputs.
        model=model,
        system_prompt=system_prompt,
        question=question,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    cached = _cache_read(key) # look in the cache for that key; if found, return it immediately without calling the API
    if cached is not None:
        return cached

    t0 = time.perf_counter()
    try: # otherwise call the Gateway API, and capture latency and token usage. If it fails, return a CandidateResult with failed=True and the error message.
        client = gateway_client().with_options(timeout=timeout_sec)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:  # never crash a run; record and continue.
        return CandidateResult(
            response="",
            latency_ms=int((time.perf_counter() - t0) * 1000),
            prompt_tokens=0,
            completion_tokens=0,
            failed=True,
            error=f"{type(e).__name__}: {e}",
        )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # if successful, parse the response and token usage. 

    try:
        text = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    except Exception as e:
        # A response without choices/usage (gateway hiccup) must not raise:
        # generate_candidate's contract is no-raise, failure rows instead.
        return CandidateResult(
            response="",
            latency_ms=latency_ms,
            prompt_tokens=0,
            completion_tokens=0,
            failed=True,
            error=f"malformed API response: {type(e).__name__}: {e}",
        )

    if not text:
        # Reasoning models (gpt-5-mini, gpt-oss, ...) spend hidden thinking
        # tokens from the same max_tokens budget; when it runs out the call
        # "succeeds" with empty visible text. Treat that as a failure so the
        # runner skips the judge (no paid calls scoring an empty string) and
        # the row is honestly candidate_failed. NOT cached: a re-run with a
        # bigger --max-tokens must retry the API call.
        return CandidateResult(
            response="",
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            failed=True,
            error=(
                "empty response: completion budget likely consumed by hidden "
                f"reasoning tokens (completion_tokens={completion_tokens}/"
                f"{max_tokens}); re-run with a larger --max-tokens"
            ),
        )

    result = CandidateResult(
        response=text,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        failed=False,
        error=None,
    )
    _cache_write(key, result)
    return result


# Smoke test — real bytes from the Gateway.
# Run:  cd evaluator && python candidate.py
# Requires DUKE_GATEWAY_URL and DUKE_GATEWAY_KEY in .env or shell env.


if __name__ == "__main__":
    system_prompt_path = (
        Path(__file__).parent / "prompts" / "system" / "it_support_v1.txt"
    )
    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    smoke_model = "gpt-5-chat"
    print(f"Calling Gateway: model={smoke_model}  (cache hit returns instantly)")
    result = generate_candidate(
        question="How do I reset my Duke NetID password?",
        model=smoke_model,
        system_prompt=system_prompt,
    )

    print()
    print("=== CandidateResult ===")
    print(f"failed:            {result.failed}")
    if result.failed:
        print(f"error:             {result.error}")
    print(f"latency_ms:        {result.latency_ms}")
    print(f"prompt_tokens:     {result.prompt_tokens}")
    print(f"completion_tokens: {result.completion_tokens}")
    print()
    print("=== response ===")
    print(result.response)
