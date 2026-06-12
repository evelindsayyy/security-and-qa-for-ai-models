"""
Compare outputs, tokens, and latency across two Duke Gateway LiteLLM models.
"""

import litellm
from litellm import RateLimitError, Timeout, APIError, APIConnectionError
import time
import os
from dataclasses import dataclass
from typing import Optional

# LiteLLM configuration for Duke Gateway (token from the repo-root .env — never hardcode)
DUKE_GATEWAY_BASE_URL = os.getenv("DUKE_GATEWAY_URL", "https://litellm.oit.duke.edu/v1")
DUKE_GATEWAY_API_KEY = os.getenv("DUKE_GATEWAY_KEY") or os.getenv("DUKE_AI_GATEWAY_API_KEY")


@dataclass
class ModelResponse:
    """Response data from a single model call."""
    model_name: str
    output: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    latency: float
    error: Optional[str] = None


def call_model(model_identifier: str, messages: list, timeout: int = 30) -> ModelResponse:
    """
    Call a single LiteLLM model on Duke Gateway.
    
    Args:
        model_identifier: Model name/identifier (e.g., "gpt-5.4", "Llama 3.3")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
    
    Returns:
        ModelResponse with output and metrics
    """
    start_time = time.time()
    
    try:
        response = litellm.completion(
            model=model_identifier,
            messages=messages,
            timeout=timeout,
            base_url=DUKE_GATEWAY_BASE_URL,
            api_key=DUKE_GATEWAY_API_KEY
        )
        
        latency = time.time() - start_time
        
        return ModelResponse(
            model_name=model_identifier,
            output=response.choices[0].message.content,
            total_tokens=response.usage.total_tokens,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            latency=latency
        )
    
    except RateLimitError as e:
        latency = time.time() - start_time
        return ModelResponse(
            model_name=model_identifier,
            output="",
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            latency=latency,
            error=f"Rate limited: {str(e)}"
        )
    except Timeout as e:
        latency = time.time() - start_time
        return ModelResponse(
            model_name=model_identifier,
            output="",
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            latency=latency,
            error=f"Request timed out: {str(e)}"
        )
    except APIError as e:
        latency = time.time() - start_time
        return ModelResponse(
            model_name=model_identifier,
            output="",
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            latency=latency,
            error=f"API error: {str(e)}"
        )
    except APIConnectionError as e:
        latency = time.time() - start_time
        return ModelResponse(
            model_name=model_identifier,
            output="",
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            latency=latency,
            error=f"Connection failed: {str(e)}"
        )


def print_model_stats(response: ModelResponse, extra_stats: bool) -> None:
    """Pretty print stats for a single model response."""
    print(f"\n{response.model_name}")
    print("-" * 60)
    
    if response.error:
        print(f"❌ Error: {response.error}")
        return
    
    print(f"Latency:              {response.latency:.3f}s")
    print(f"Total Tokens:         {response.total_tokens}")
    
    if extra_stats:
        print(f"Prompt Tokens:        {response.prompt_tokens}")
        print(f"Completion Tokens:    {response.completion_tokens}")
        if response.latency > 0:
            print(f"Tokens/Second:        {response.completion_tokens / response.latency:.2f}")
    
    print(f"\nOutput:")
    print(response.output)


if __name__ == "__main__":
    prompt = "Tell me a funny joke"
    system_prompt = ""
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    
    print(f"Prompt: {prompt}\n")
    print("=" * 60)
    
    # Call first model
    print(f"\nCalling gpt-5.4...", flush=True)
    response1 = call_model("openai/gpt-5.4", messages)
    print_model_stats(response1, extra_stats=False)
    
    # Call second model
    print(f"\n\nCalling Llama 3.3...", flush=True)
    response2 = call_model("openai/Llama 3.3", messages)
    print_model_stats(response2, extra_stats=False)
    
    # Call third model
    print(f"\n\nCalling gpt-5-mini...", flush=True)
    response3 = call_model("openai/gpt-5-mini", messages)
    print_model_stats(response3, extra_stats=False)
