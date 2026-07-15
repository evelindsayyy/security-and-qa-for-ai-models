"""Tests for the fake vLLM stub (scripts/dev/fake_vllm.py).

Uses Flask's test client — no real port binding, so this runs the same as
any other unit test and doesn't need a free port or a running process.
"""

from __future__ import annotations

import unittest

from scripts.dev.fake_vllm import build_app


class FakeVllmTest(unittest.TestCase):
    def setUp(self) -> None:
        app = build_app(model="fake-model", response_text="I cannot help with that.")
        self.client = app.test_client()

    def test_health_returns_200(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_chat_completions_shape_matches_openai(self) -> None:
        resp = self.client.post(
            "/v1/chat/completions",
            json={"model": "fake-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(
            body["choices"][0]["message"]["content"],
            "I cannot help with that.",
        )
        self.assertEqual(body["model"], "fake-model")

    def test_chat_completions_echoes_requested_model(self) -> None:
        resp = self.client.post(
            "/v1/chat/completions",
            json={"model": "org/other-model", "messages": []},
        )
        self.assertEqual(resp.get_json()["model"], "org/other-model")

    def test_missing_model_falls_back_to_default(self) -> None:
        resp = self.client.post("/v1/chat/completions", json={"messages": []})
        self.assertEqual(resp.get_json()["model"], "fake-model")


if __name__ == "__main__":
    unittest.main()
