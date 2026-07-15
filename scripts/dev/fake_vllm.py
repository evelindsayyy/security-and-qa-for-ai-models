#!/usr/bin/env python3
"""
Fake vLLM — a minimal stand-in for a self-hosted OpenAI-compatible server.

Answers /health and /v1/chat/completions in the same shape a real vLLM
server would, but always with the same canned reply regardless of what's
asked. Lets you run the full --hf-repo pipeline (safety/run.py ->
run_garak.py --base-url / promptfoo's GATEWAY_BASE_URL) against a real,
running server — without a GPU or a DCC session — to prove the plumbing
(URL wiring, request/response parsing, report writing) actually works.

This does NOT test whether a real model is safe — every probe gets the
same canned answer. It only proves the pipeline's plumbing is correct.

Run:
    uv run python -m scripts.dev.fake_vllm --port 8000 --model Qwen/Qwen2.5-3B-Instruct

Then point the safety pipeline at it:
    uv run python -m safety.run --hf-repo Qwen/Qwen2.5-3B-Instruct \\
        --endpoint http://localhost:8000/v1 --skip-redteam

Docker note: garak runs directly on the host, so http://localhost:PORT/v1
reaches this server fine. Promptfoo runs inside its own Docker container
(safety/promptfoo/docker/compose.yml), and a container's "localhost" is
itself, not the host — so --skip-garak runs need the Docker bridge gateway
IP instead, e.g. http://172.17.0.1:8000/v1 on Linux (find yours with
`docker network inspect bridge --format '{{range .IPAM.Config}}{{.Gateway}}{{end}}'`).
"""

from __future__ import annotations

import argparse
import time

from flask import Flask, jsonify, request

DEFAULT_RESPONSE = "I cannot help with that."


def build_app(*, model: str, response_text: str) -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return "", 200

    @app.post("/v1/chat/completions")
    def chat_completions():
        payload = request.get_json(silent=True) or {}
        requested_model = payload.get("model", model)
        return jsonify({
            "id": "fake-vllm-0",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": requested_model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    return app


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--model", default="fake-model", help="echoed back in responses if the request omits one")
    ap.add_argument("--response", default=DEFAULT_RESPONSE, help="canned assistant reply for every request")
    args = ap.parse_args(argv)

    app = build_app(model=args.model, response_text=args.response)
    print(f"[fake_vllm] serving http://0.0.0.0:{args.port}/v1  (model={args.model!r})", flush=True)
    app.run(host="0.0.0.0", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
