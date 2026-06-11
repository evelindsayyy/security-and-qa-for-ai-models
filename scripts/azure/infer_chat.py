#!/usr/bin/env python3
"""Send a single chat-completions request to a Foundry deployment."""

from __future__ import annotations

import argparse
import json
import os
import sys

from openai import OpenAI


DEFAULT_TIMEOUT = 120
BASE_URL_ENV_NAMES = (
    "FOUNDRY_BASE_URL",
    "FOUNDRY_ENDPOINT",
    "OPENAI_BASE_URL",
    "AZURE_OPENAI_ENDPOINT",
)
API_KEY_ENV_NAMES = (
    "FOUNDRY_API_KEY",
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_INFERENCE_CREDENTIAL",
)
MODEL_ENV_NAMES = (
    "FOUNDRY_MODEL",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_MODEL",
)


def normalize_openai_base_url(endpoint: str) -> str:
    """Normalize a Foundry or Azure OpenAI endpoint to an OpenAI v1 base URL."""
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith("/openai/v1"):
        return endpoint
    return endpoint + "/openai/v1"


def build_chat_payload(
    *,
    model: str,
    prompt: str,
    max_tokens: int,
    system: str | None,
) -> dict:
    """Build a minimal chat-completions payload."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }


def require_first_env(names: tuple[str, ...]) -> str:
    """Return the first configured variable from a set of aliases."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise SystemExit(f"Missing required environment variable. Tried: {', '.join(names)}")


def first_env(names: tuple[str, ...]) -> str | None:
    """Return the first configured alias value, if any."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def build_client(base_url: str, api_key: str) -> OpenAI:
    """Create an OpenAI client for a Foundry-compatible endpoint."""
    return OpenAI(base_url=base_url, api_key=api_key)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for a one-shot inference request."""
    parser = argparse.ArgumentParser(
        description="Send a single chat completion request to a Foundry deployment."
    )
    parser.add_argument("--prompt", required=True, help="User prompt to send")
    parser.add_argument("--model", help="Deployment name or model name")
    parser.add_argument("--system", help="Optional system prompt")
    parser.add_argument("--max-tokens", type=int, default=256, help="Maximum output tokens")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Request timeout in seconds",
    )
    return parser.parse_args()


def main() -> int:
    """Run a one-shot Foundry inference call and print the JSON response."""
    args = parse_args()
    endpoint = require_first_env(BASE_URL_ENV_NAMES)
    api_key = require_first_env(API_KEY_ENV_NAMES)
    model = args.model or first_env(MODEL_ENV_NAMES)
    if not model:
        raise SystemExit(
            "Provide --model or set one of: " + ", ".join(MODEL_ENV_NAMES)
        )

    client = build_client(
        base_url=normalize_openai_base_url(endpoint),
        api_key=api_key,
    )
    payload = build_chat_payload(
        model=model,
        prompt=args.prompt,
        max_tokens=args.max_tokens,
        system=args.system,
    )
    response = client.chat.completions.create(
        model=payload["model"],
        messages=payload["messages"],
        max_tokens=payload["max_tokens"],
        timeout=args.timeout,
    )
    json.dump(response.model_dump(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
