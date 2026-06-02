"""
_gateway.py

Shared Duke AI Gateway client wiring used by candidate.py and judge.py.
Lazy, module-scoped — one OpenAI client per process, built on first use.

Environment:
    DUKE_GATEWAY_URL   OpenAI-compatible endpoint root for LiteLLM
                       (typically ``https://litellm.oit.duke.edu/v1``).
    DUKE_GATEWAY_KEY   LiteLLM API key. Loaded from .env via python-dotenv;
                       a shell-exported value takes precedence.

Underscore prefix marks this as evaluator-internal: external callers
should reach the Gateway via the public ``generate_candidate`` and
``judge_response`` functions, not by importing this module directly.
"""
#both candidate.py and judge.py need to talk to the Gateway, but we want to avoid redundant client-building code in each. This module centralizes the
#client wiring and env var handling. The client is built lazily on first use, so importing this module doesn't immediately require the env vars to be set — only when you actually call gateway_client().

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI


# Load .env once on import. ``override=False`` so a shell-exported env var
# wins over .env — useful when a teammate wants to point at a different
# Gateway without editing the file.
load_dotenv(override=False)


GATEWAY_URL_ENV = "DUKE_GATEWAY_URL"
GATEWAY_KEY_ENV = "DUKE_GATEWAY_KEY"


_CLIENT: Optional[OpenAI] = None


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"{name} is not set. Add it to .env (or export it in your shell) "
            f"before calling Gateway-backed code. See evaluator/CLAUDE.md."
        )
    return val


def gateway_client() -> OpenAI:
    """Return the lazily-built shared OpenAI client pointed at the Gateway."""
    global _CLIENT
    if _CLIENT is None:
        # base_url should be the OpenAI-compatible endpoint root. LiteLLM
        # convention is <host>/v1 — we trust the env var verbatim rather
        # than silently rewriting it.
        _CLIENT = OpenAI(
            base_url=_require_env(GATEWAY_URL_ENV),
            api_key=_require_env(GATEWAY_KEY_ENV),
        )
    return _CLIENT
