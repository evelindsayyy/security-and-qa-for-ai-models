from __future__ import annotations

import os
import re
import time
import subprocess
import requests

from litellm import completion
from urllib.parse import urlparse

from benchmark_run_stats import get_active_run_stats

DEFAULT_MAX_RETRIES = max(1, int(os.getenv("BENCHMARK_MAX_RETRIES", "3")))
DEFAULT_RETRY_DELAY_SEC = float(os.getenv("BENCHMARK_RETRY_DELAY_SEC", "1.0"))

# LiteLLM routes by the first path segment of the model id (e.g. huggingface/…).
_KNOWN_LITELLM_PREFIXES = frozenset({
    "openai",
    "anthropic",
    "huggingface",
    "groq",
    "together",
    "fireworks",
    "gemini",
    "openrouter",
    "azure",
    "bedrock",
    "cohere",
    "mistral",
    "ollama",
    "hosted_vllm",
})


class EmptyModelResponseError(RuntimeError):
    """All retries exhausted and the model returned no usable text."""


def _fatal_error_hint(exc: Exception) -> str | None:
    """Short, actionable hint for known *non-retryable* errors (else None).

    These come back from hosted endpoints (e.g. HF Inference Providers) and
    won't change across retries, so we surface a friendly one-liner instead of
    spamming the raw LiteLLM stack trace three times per question.
    """
    msg = str(exc).lower()
    if "not supported by any provider" in msg:
        return (
            "model isn't routed — enable the provider on your HF account "
            "(huggingface.co/settings/inference-providers, or set to auto), "
            "or pin one from the model page with org/model:provider "
            "(e.g. TinyLlama/TinyLlama-1.1B-Chat-v1.0:featherless-ai)"
        )
    if (
        "depleted your monthly included credits" in msg
        or "purchase pre-paid credits" in msg
        or "error code: 402" in msg
    ):
        return (
            "Hugging Face Inference Providers credits exhausted — wait for the "
            "monthly reset, upgrade to PRO, or run against your own vLLM endpoint"
        )
    return None


def detect_provider(base_url: str) -> str:
    """
    Infer the backend/provider from an API base URL.

    Returns one of:
        duke
        openai
        openrouter
        anthropic
        google
        groq
        together
        fireworks
        huggingface
        vllm
        openai_compatible
    """

    if not base_url:
        return "openai_compatible"

    host = urlparse(base_url).netloc.lower()

    if "litellm.oit.duke.edu" in host:
        return "duke"

    if "api.openai.com" in host:
        return "openai"

    if "openrouter.ai" in host:
        return "openrouter"

    if "api.anthropic.com" in host:
        return "anthropic"

    if "generativelanguage.googleapis.com" in host:
        return "google"

    if "api.groq.com" in host:
        return "groq"

    if "api.together.xyz" in host:
        return "together"

    if "api.fireworks.ai" in host:
        return "fireworks"

    # The HF Inference Providers router is OpenAI-compatible (base_url + model
    # id, like the OpenAI SDK), unlike the retired api-inference.* path. Since
    # callers always pass api_base, route it through the openai path so we POST
    # to <router>/v1/chat/completions instead of LiteLLM's HF TGI transform.
    if "router.huggingface.co" in host:
        return "openai_compatible"

    if (
        "huggingface.co" in host
        or "hf.space" in host
        or host.startswith("api-inference.")
    ):
        return "huggingface"

    if host.startswith("localhost") or host.startswith("127.0.0.1"):
        return "vllm"

    return "openai_compatible"

def _has_litellm_provider_prefix(model: str) -> bool:
    if "/" not in model:
        return False
    prefix = model.split("/", 1)[0].lower()
    return prefix in _KNOWN_LITELLM_PREFIXES or prefix.startswith("azure")


def normalize_model(model: str, base_url: str) -> str:
    """
    Normalize model names for LiteLLM.

    LiteLLM needs an explicit provider prefix for many backends (Hugging Face
    repo ids, local vLLM, Duke gateway display names, etc.).
    """
    if _has_litellm_provider_prefix(model):
        return model

    provider = detect_provider(base_url)

    if provider == "duke":
        if "/" not in model:
            return f"openai/{model}"
        return model

    if provider == "huggingface":
        return f"huggingface/{model}"

    if provider in {"vllm", "openai_compatible"}:
        return f"openai/{model}"

    return model


def response_content(response) -> str:
    """Extract assistant text from a LiteLLM completion response."""
    if response is None:
        return ""
    try:
        choices = getattr(response, "choices", None)
        if not choices:
            return ""
        first = choices[0]
        message = getattr(first, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if content is not None and str(content).strip():
                return str(content).strip()
        text = getattr(first, "text", None)
        if text is not None and str(text).strip():
            return str(text).strip()
    except (AttributeError, IndexError, TypeError):
        pass
    return ""


def response_usage(response) -> dict[str, int] | None:
    """Extract token usage from a LiteLLM completion response, if present."""
    if response is None:
        return None
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return None
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        completion_tok = usage.get("completion_tokens")
        total = usage.get("total_tokens")
    else:
        prompt = getattr(usage, "prompt_tokens", None)
        completion_tok = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
    if prompt is None and completion_tok is None and total is None:
        return None
    out: dict[str, int] = {}
    if prompt is not None:
        out["prompt_tokens"] = int(prompt)
    if completion_tok is not None:
        out["completion_tokens"] = int(completion_tok)
    if total is not None:
        out["total_tokens"] = int(total)
    elif out:
        out["total_tokens"] = out.get("prompt_tokens", 0) + out.get("completion_tokens", 0)
    return out or None


_REASONING_BLOCK = re.compile(
    r"<(think|thinking|reason|reasoning|scratchpad)>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
_REASONING_TAG = re.compile(
    r"</?(think|thinking|reason|reasoning|scratchpad)>",
    re.IGNORECASE,
)


def strip_reasoning(text: str) -> str:
    """Remove chain-of-thought blocks emitted by reasoning models.

    Provider-agnostic: handles Qwen3 / DeepSeek-R1 ``<think>`` tags and the
    other common reasoning tag names. An unterminated opening tag (model ran
    out of tokens mid-thought) is also dropped so the trailing answer survives.
    """
    if not text:
        return ""
    cleaned = _REASONING_BLOCK.sub(" ", text)
    cleaned = _REASONING_TAG.sub(" ", cleaned)
    return cleaned.strip()


def extract_choice_letter(text: str, letters: str = "ABCD") -> str:
    """Extract a single multiple-choice letter from a model response.

    Works across models (not just Qwen) and fixes the historical parsing bugs:
      - returning the letter found *inside* an ordinary word ("A" in "watermelon")
      - matching the English article "a"/"A" after uppercasing the whole reply
      - reasoning traces leaking into the parsed answer
    Only standalone letters in the valid set count; matching prefers an
    explicit answer phrase, then option punctuation, then the last bare letter.
    """
    if not text:
        return ""
    cleaned = strip_reasoning(text)
    if not cleaned:
        return ""

    upper = letters.upper()

    # 0) The whole reply is just the letter (any case), maybe with punctuation.
    bare = cleaned.strip().strip(".):(*# \t\r\n").strip()
    if len(bare) == 1 and bare.upper() in upper:
        return bare.upper()

    # 1) Explicit answer phrase: "The answer is C", "Answer: B".
    m = re.search(rf"answer\b[^A-Za-z]{{0,20}}([{upper}])\b", cleaned, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # 2) A letter next to option punctuation: "C.", "B)", "(D)".
    m = re.search(rf"(?<![A-Za-z])([{upper}])\s*[).:]", cleaned)
    if m:
        return m.group(1).upper()

    # 3) Fall back to the last standalone UPPERCASE letter in the valid set.
    #    Uppercase-only, so the article "a" / letters inside words never match.
    matches = re.findall(rf"(?<![A-Za-z])([{upper}])(?![A-Za-z])", cleaned)
    if matches:
        return matches[-1].upper()

    return ""


def query_chat_completion(
    *,
    model: str,
    base_url: str,
    api_key: str,
    messages: list,
    temperature: float = 0,
    max_tokens: int | None = None,
    max_retries: int | None = None,
    require_non_empty: bool = True,
):
    """
    Call LiteLLM chat completions with retries on API errors and blank output.

    Set BENCHMARK_MAX_RETRIES / BENCHMARK_RETRY_DELAY_SEC in the environment
    to tune retry behavior for all benchmark scripts.
    """
    normalized = normalize_model(model, base_url)
    retries = max(1, max_retries if max_retries is not None else DEFAULT_MAX_RETRIES)

    last_exc: Exception | None = None
    response = None
    tokens = max_tokens

    for attempt in range(1, retries + 1):
        kwargs = {
            "model": normalized,
            "api_base": base_url,
            "api_key": api_key,
            "messages": messages,
            "temperature": temperature,
        }
        if tokens is not None:
            kwargs["max_tokens"] = tokens

        stats = get_active_run_stats()
        t0 = time.perf_counter()
        try:
            response = completion(**kwargs)
            latency_ms = (time.perf_counter() - t0) * 1000
            if response_content(response) or not require_non_empty:
                if stats is not None:
                    stats.record_success(latency_ms, response_usage(response))
                return response
            last_exc = EmptyModelResponseError(
                f"empty response from {model!r} (attempt {attempt}/{retries})"
            )
            if stats is not None:
                stats.record_failure(latency_ms)
            print(f"  [WARN] empty model response, retrying ({attempt}/{retries})...")
            if tokens is not None and tokens < 2048:
                tokens = min(tokens * 2, 2048)
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            last_exc = exc
            hint = _fatal_error_hint(exc)
            if hint is not None:
                if stats is not None:
                    stats.record_failure(latency_ms)
                print(f"  [ERROR] {hint}")
                break
            if stats is not None:
                stats.record_failure(latency_ms)
            print(f"  [WARN] completion failed ({attempt}/{retries}): {exc}")

        if attempt < retries:
            time.sleep(DEFAULT_RETRY_DELAY_SEC * attempt)

    if last_exc is not None and require_non_empty:
        raise last_exc
    return response


def launch_local_model(
    model_id: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    timeout: int = 300,
):
    """
    Launch a local vLLM server and wait for it to become ready.

    Returns:
        {
            "process": proc,
            "base_url": "...",
            "model": model_id,
            "api_key": "dummy",
        }
    """

    cmd = [
        "vllm",
        "serve",
        model_id,
        "--host",
        host,
        "--port",
        str(port),
    ]

    proc = subprocess.Popen(cmd)

    base_url = f"http://{host}:{port}/v1"

    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/models", timeout=5)

            if r.status_code == 200:
                return {
                    "process": proc,
                    "base_url": base_url,
                    "model": model_id,
                    "api_key": "dummy",
                }

        except requests.RequestException:
            pass

        time.sleep(2)

    proc.kill()

    raise RuntimeError(
        f"Timed out waiting for vLLM to start for {model_id}"
    )