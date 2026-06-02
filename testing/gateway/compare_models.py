#!/usr/bin/env python3
"""Compare latency and token usage across gateway models (LiteLLM)."""

from __future__ import annotations

import argparse

from duke_gateway import ModelResponse, call_model


def print_stats(response: ModelResponse, verbose: bool) -> None:
    print(f"\n{response.model_name}")
    print("-" * 60)
    if response.error:
        print(f"Error: {response.error}")
        return
    print(f"Latency:       {response.latency:.3f}s")
    print(f"Total tokens:  {response.total_tokens}")
    if verbose:
        print(f"Prompt tokens: {response.prompt_tokens}")
        print(f"Completion:    {response.completion_tokens}")
        if response.latency > 0:
            tps = response.completion_tokens / response.latency
            print(f"Tokens/sec:    {tps:.2f}")
    print(f"\nOutput:\n{response.output}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", default="Tell me a funny joke")
    p.add_argument(
        "--models",
        nargs="+",
        default=["openai/gpt-5.4", "openai/Llama 3.3", "openai/gpt-5-mini"],
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    messages = [
        {"role": "system", "content": ""},
        {"role": "user", "content": args.prompt},
    ]
    print(f"Prompt: {args.prompt}\n{'=' * 60}")
    for model in args.models:
        print(f"\nCalling {model}...", flush=True)
        print_stats(call_model(model, messages), args.verbose)


if __name__ == "__main__":
    main()
