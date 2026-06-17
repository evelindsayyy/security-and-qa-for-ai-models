from __future__ import annotations

import os
import time

from litellm import completion

DEFAULT_MAX_RETRIES = max(1, int(os.getenv("BENCHMARK_MAX_RETRIES", "3")))
DEFAULT_RETRY_DELAY_SEC = float(os.getenv("BENCHMARK_RETRY_DELAY_SEC", "1.0"))


class EmptyModelResponseError(RuntimeError):
    """All retries exhausted and the model returned no usable text."""


def normalize_model(model: str, base_url: str) -> str:
    """
    Normalize model names for LiteLLM.

    Duke AI Gateway requires openai/ prefixes for some models
    when using the LiteLLM Python package.
    """

    if "/" in model:
        return model

    if "litellm.oit.duke.edu" in base_url:
        return f"openai/{model}"

    # Add more conditions for other base URLs later

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

        try:
            response = completion(**kwargs)
            if response_content(response) or not require_non_empty:
                return response
            last_exc = EmptyModelResponseError(
                f"empty response from {model!r} (attempt {attempt}/{retries})"
            )
            print(f"  [WARN] empty model response, retrying ({attempt}/{retries})...")
            if tokens is not None and tokens < 2048:
                tokens = min(tokens * 2, 2048)
        except Exception as exc:
            last_exc = exc
            print(f"  [WARN] completion failed ({attempt}/{retries}): {exc}")

        if attempt < retries:
            time.sleep(DEFAULT_RETRY_DELAY_SEC * attempt)

    if last_exc is not None and require_non_empty:
        raise last_exc
    return response
