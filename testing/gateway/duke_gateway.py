"""Shared LiteLLM helpers for Duke AI Gateway (OpenAI-compatible)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import litellm
from litellm import APIConnectionError, APIError, RateLimitError, Timeout

DUKE_GATEWAY_BASE_URL = os.getenv(
    "DUKE_GATEWAY_BASE_URL", "https://litellm.oit.duke.edu/v1"
)
DUKE_GATEWAY_API_KEY_ENV = "DUKE_AI_GATEWAY_API_KEY"


def get_api_key() -> str:
    key = os.getenv(DUKE_GATEWAY_API_KEY_ENV)
    if not key:
        raise RuntimeError(
            f"Set {DUKE_GATEWAY_API_KEY_ENV} in the environment (see .env.example). "
            "Never commit API keys."
        )
    return key


@dataclass
class ModelResponse:
    model_name: str
    output: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    latency: float
    error: Optional[str] = None


def call_model(
    model_identifier: str,
    messages: list[dict[str, str]],
    timeout: int = 30,
) -> ModelResponse:
    start_time = time.time()
    try:
        response = litellm.completion(
            model=model_identifier,
            messages=messages,
            timeout=timeout,
            base_url=DUKE_GATEWAY_BASE_URL,
            api_key=get_api_key(),
        )
        latency = time.time() - start_time
        usage = response.usage
        return ModelResponse(
            model_name=model_identifier,
            output=response.choices[0].message.content or "",
            total_tokens=usage.total_tokens,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            latency=latency,
        )
    except RateLimitError as e:
        return _error_response(model_identifier, start_time, f"Rate limited: {e}")
    except Timeout as e:
        return _error_response(model_identifier, start_time, f"Request timed out: {e}")
    except APIError as e:
        return _error_response(model_identifier, start_time, f"API error: {e}")
    except APIConnectionError as e:
        return _error_response(model_identifier, start_time, f"Connection failed: {e}")


def _error_response(model: str, start_time: float, message: str) -> ModelResponse:
    latency = time.time() - start_time
    return ModelResponse(
        model_name=model,
        output="",
        total_tokens=0,
        prompt_tokens=0,
        completion_tokens=0,
        latency=latency,
        error=message,
    )


def chain_models(
    first_model: str,
    second_model: str,
    initial_prompt: str,
    system1_prompt: str = "",
    system2_prompt: str = "",
    second_prompt_template: str | None = None,
    timeout: int = 30,
) -> tuple[ModelResponse, ModelResponse]:
    """Call first model, then pass its output into the second (e.g. judge pattern)."""
    messages1 = [
        {"role": "system", "content": system1_prompt},
        {"role": "user", "content": initial_prompt},
    ]
    response1 = call_model(first_model, messages1, timeout=timeout)
    if response1.error:
        skipped = ModelResponse(
            model_name=second_model,
            output="",
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            latency=0.0,
            error=f"Skipped second model: {response1.error}",
        )
        return response1, skipped

    second_prompt = (
        second_prompt_template.format(
            original_prompt=initial_prompt,
            output=response1.output,
        )
        if second_prompt_template
        else (
            f"Original question: {initial_prompt}\n\n"
            f"First model output:\n{response1.output}"
        )
    )
    messages2 = [
        {"role": "system", "content": system2_prompt},
        {"role": "user", "content": second_prompt},
    ]
    response2 = call_model(second_model, messages2, timeout=timeout)
    return response1, response2
