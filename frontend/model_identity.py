"""
Shared model-identity normalization for the two identity spaces that exist
in this app — they are intentionally kept separate, not collapsed into one
universal key:

- **Gateway id space** (safety, evaluator, benchmarks) — a Duke AI Gateway
  LiteLLM model id ("GPT 4.1 Mini").
- **HF repo id space** (scanner) — a Hugging Face repo id
  ("BAAI/bge-small-en-v1.5").

There is no mapping table between the two (a shared `models` table is
deferred future work); a model scanned on disk and a model reachable through
the gateway are not assumed to be the same thing unless their ids literally match.
"""

from __future__ import annotations

from safety.gateway_ids import normalize_gateway_model_id
from scanner.paths import safe_dir_name, slug_to_model_id


def gateway_slug(raw: str) -> str:
    """Canonical slug for a gateway model id — same normalization safety
    already uses, re-exported so eval/benchmark/rollup code shares it too."""
    return normalize_gateway_model_id(raw)


def hf_slug(repo_id: str) -> str:
    """HF repo id -> output-dir slug (``BAAI/bge`` -> ``BAAI--bge``) — same
    convention ``scanner/paths.py`` already uses everywhere on disk."""
    return safe_dir_name(repo_id)


def hf_repo_id(slug: str) -> str:
    """Output-dir slug -> HF repo id for display (``BAAI--bge`` -> ``BAAI/bge``)."""
    return slug_to_model_id(slug)


def gateway_is_hf_scannable(gateway_model_id: str) -> bool:
    """True when an HF artifact scan is meaningful for this gateway model."""
    lower = gateway_model_id.lower()
    return "llama" in lower or "gpt-oss" in lower
