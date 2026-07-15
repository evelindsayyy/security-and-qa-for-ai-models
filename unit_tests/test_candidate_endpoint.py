"""
Unit tests for the candidate endpoint override (self-hosted models).

What must hold:
  1. Cache-key backward compatibility — endpoint=None produces the exact
     pre-override key, so every existing cache entry stays valid.
  2. Endpoint isolation — the same inputs served by different endpoints get
     different cache keys (a local vLLM build of "model X" must never collide
     with the Gateway's "model X").
  3. Client routing — endpoint=None routes to the shared Gateway client;
     an endpoint gets its own client (cached per URL) with that base_url.
  4. The no-raise contract survives an unreachable endpoint — a dead URL
     yields failed=True, not an exception.

Run from repo root:
  uv run python -m unittest unit_tests.test_candidate_endpoint -v
"""

from __future__ import annotations

import hashlib
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

_EVALUATOR = Path(__file__).resolve().parent.parent / "evaluator"
sys.path.insert(0, str(_EVALUATOR))

import candidate  # noqa: E402


class TestCacheKeyEndpoint(unittest.TestCase):
    KW = dict(
        model="m", system_prompt="s", question="q",
        temperature=0.2, max_tokens=500,
    )

    def test_default_key_is_byte_identical_to_pre_override_format(self):
        """endpoint=None must reproduce the historical key so the existing
        cache directory keeps hitting."""
        expected = hashlib.sha256(b"m|s|q|0.2000|500").hexdigest()
        self.assertEqual(candidate._cache_key(**self.KW), expected)
        self.assertEqual(candidate._cache_key(**self.KW, endpoint=None), expected)

    def test_endpoint_changes_the_key(self):
        base = candidate._cache_key(**self.KW)
        vllm = candidate._cache_key(**self.KW, endpoint="http://localhost:8000/v1")
        ollama = candidate._cache_key(**self.KW, endpoint="http://localhost:11434/v1")
        self.assertNotEqual(base, vllm)
        self.assertNotEqual(base, ollama)
        self.assertNotEqual(vllm, ollama)


class TestClientRouting(unittest.TestCase):
    def setUp(self):
        candidate._ENDPOINT_CLIENTS.clear()

    def test_none_routes_to_gateway_client(self):
        sentinel = object()
        with mock.patch.object(candidate, "gateway_client", return_value=sentinel) as gw:
            self.assertIs(candidate._client_for(None), sentinel)
            gw.assert_called_once()

    def test_endpoint_builds_and_caches_its_own_client(self):
        url = "http://localhost:8000/v1"
        c1 = candidate._client_for(url)
        c2 = candidate._client_for(url)
        self.assertIs(c1, c2)                       # cached per URL
        self.assertEqual(str(c1.base_url), url + "/")  # OpenAI normalizes with trailing /
        # and it never touched the Gateway client
        with mock.patch.object(candidate, "gateway_client") as gw:
            candidate._client_for(url)
            gw.assert_not_called()


class TestUnreachableEndpointNoRaise(unittest.TestCase):
    def test_dead_endpoint_returns_failed_result(self):
        # Port 9 (discard) on localhost: nothing listens; connection refused.
        # Unique question -> guaranteed cache miss, and failures are never
        # cached so this leaves nothing behind.
        result = candidate.generate_candidate(
            question=f"unreachable-{uuid.uuid4()}",
            model="any-model",
            system_prompt="s",
            timeout_sec=2.0,
            endpoint="http://127.0.0.1:9/v1",
        )
        self.assertTrue(result.failed)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.response, "")


class TestTemperatureRetry(unittest.TestCase):
    _TEMP_ERR = Exception(
        "Unsupported value: 'temperature' does not support 0.2 with this "
        "model. Only the default (1) value is supported."
    )

    def test_predicate(self):
        self.assertTrue(candidate._is_temperature_unsupported(self._TEMP_ERR))
        self.assertFalse(candidate._is_temperature_unsupported(Exception("rate limit")))
        self.assertFalse(candidate._is_temperature_unsupported(Exception("budget exceeded")))

    def test_retries_at_temperature_1_on_unsupported(self):
        msg = mock.Mock(content="hello")
        good = mock.Mock(choices=[mock.Mock(message=msg)],
                         usage=mock.Mock(prompt_tokens=3, completion_tokens=2))
        client = mock.Mock()
        client.chat.completions.create.side_effect = [self._TEMP_ERR, good]
        inner = mock.Mock()
        inner.with_options.return_value = client
        with mock.patch.object(candidate, "_client_for", return_value=inner), \
             mock.patch.object(candidate, "_cache_write"):
            r = candidate.generate_candidate(
                question=f"t-{uuid.uuid4()}", model="gpt-5.1-chat",
                system_prompt="s", temperature=0.2,
            )
        self.assertFalse(r.failed)
        self.assertEqual(r.response, "hello")
        calls = client.chat.completions.create.call_args_list
        self.assertEqual(len(calls), 2)                       # first + retry
        self.assertEqual(calls[0].kwargs["temperature"], 0.2)  # requested
        self.assertEqual(calls[1].kwargs["temperature"], 1.0)  # retry

    def test_other_errors_are_not_retried(self):
        client = mock.Mock()
        client.chat.completions.create.side_effect = Exception("429 rate limit")
        inner = mock.Mock()
        inner.with_options.return_value = client
        with mock.patch.object(candidate, "_client_for", return_value=inner):
            r = candidate.generate_candidate(
                question=f"t-{uuid.uuid4()}", model="m", system_prompt="s",
            )
        self.assertTrue(r.failed)
        self.assertEqual(client.chat.completions.create.call_count, 1)  # no retry


if __name__ == "__main__":
    unittest.main()
