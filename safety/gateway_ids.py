"""
Normalize gateway model strings to ``models.gateway_model_id`` form.

See ``docs/gateway-models.md`` (LiteLLM display names) and
``docs/data-model.md`` (canonical id example: ``gpt-4.1-mini``).

Spike exports may use provider labels (``duke-gpt-4.1-mini``), Promptfoo ids
(``openai:chat:GPT 4.1 Mini``), or Garak ``target_name`` (``GPT 4.1 Mini``).
All must collapse to one slug for ``safety/output/<slug>/`` and the frontend.
"""

from __future__ import annotations

import re


def normalize_gateway_model_id(raw: str) -> str:
    """
    Coerce tool-specific labels into a stable lowercase hyphenated id.

    Examples:
        ``GPT 4.1 Mini`` → ``gpt-4.1-mini``
        ``duke-gpt-4.1-mini`` → ``gpt-4.1-mini``
        ``openai:chat:GPT 4.1 Mini`` → ``gpt-4.1-mini``
    """
    s = (raw or "").strip()
    if not s:
        return "unknown"

    # promptfoo label prefix from run_safety.sh
    if s.lower().startswith("duke-"):
        s = s[5:]

    # strip openai:chat: etc. — keep the LiteLLM display name tail
    if ":" in s:
        s = s.rsplit(":", 1)[-1].strip()

    s = s.lower().replace(" ", "-")
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "unknown"


def display_name_from_id(gateway_model_id: str) -> str:
    """Best-effort display name for nutrition-label UI (not authoritative)."""
    parts = gateway_model_id.replace("-", " ").split()
    out: list[str] = []
    for p in parts:
        if p.upper() in ("GPT", "OSS"):
            out.append(p.upper())
        elif p.isdigit() or re.match(r"^\d", p):
            out.append(p)
        else:
            out.append(p.capitalize())
    return " ".join(out)
