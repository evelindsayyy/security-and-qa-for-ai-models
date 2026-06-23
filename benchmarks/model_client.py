from __future__ import annotations

import os
import re
import time
import subprocess
import requests

from litellm import completion
from urllib.parse import urlparse

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