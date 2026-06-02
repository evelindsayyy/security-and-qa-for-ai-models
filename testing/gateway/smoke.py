#!/usr/bin/env python3
"""Single-request gateway smoke test (LiteLLM)."""

from __future__ import annotations

import argparse

from duke_gateway import call_model


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--prompt", default="Reply with one word: ok")
    args = p.parse_args()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": args.prompt},
    ]
    r = call_model(args.model, messages)
    if r.error:
        print(r.error)
        raise SystemExit(1)
    print(f"Latency: {r.latency:.2f}s")
    print(f"Tokens:  {r.total_tokens}")
    print(r.output)


if __name__ == "__main__":
    main()
