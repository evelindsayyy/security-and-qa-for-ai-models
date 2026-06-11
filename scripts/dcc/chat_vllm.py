#!/usr/bin/env python3
"""Send a prompt to a running local vLLM server via its OpenAI-compatible API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from openai import OpenAI


SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = SCRIPT_DIR / ".vllm-session.env"


def normalize_vllm_base_url(host: str, port: int) -> str:
    """Build the OpenAI-compatible base URL for a local vLLM server."""
    return f"http://{host}:{port}/v1"


def build_chat_payload(
    *,
    model: str,
    prompt: str,
    max_tokens: int,
    system: str | None,
) -> dict:
    """Build a minimal chat-completions payload for the local server."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }


def load_state_file() -> dict[str, str]:
    """Load host, port, and model details from the local session file if present."""
    if not STATE_FILE.exists():
        return {}

    result: dict[str, str] = {}
    for line in STATE_FILE.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value.strip().strip('"')
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for a one-shot local vLLM request."""
    parser = argparse.ArgumentParser(
        description="Send a prompt to a running local vLLM server."
    )
    parser.add_argument("--host", help="Host running vLLM")
    parser.add_argument("--port", type=int, help="Port exposed by vLLM")
    parser.add_argument("--model", help="Model name expected by the server")
    parser.add_argument("--prompt", required=True, help="Prompt to send")
    parser.add_argument("--system", help="Optional system prompt")
    parser.add_argument("--max-tokens", type=int, default=256, help="Maximum output tokens")
    parser.add_argument("--timeout", type=int, default=120, help="Request timeout in seconds")
    return parser.parse_args()


def main() -> int:
    """Send the prompt to vLLM and print the JSON response."""
    args = parse_args()
    state = load_state_file()
    host = args.host or state.get("HOST") or "localhost"
    port = args.port or int(state.get("PORT", "8000"))
    model = args.model or state.get("MODEL")
    if not model:
        raise SystemExit("Provide --model or start a vLLM session first.")

    client = OpenAI(
        base_url=normalize_vllm_base_url(host, port),
        api_key=os.getenv("VLLM_API_KEY", "local-vllm"),
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
