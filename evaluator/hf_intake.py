"""
hf_intake.py — validate a Hugging Face model BEFORE serving it for evaluation.

Step 1 of the self-serve flow (HF link -> DCC serve -> eval -> report card):
given a user-supplied repo id, decide whether we can evaluate it *before*
spawning any cluster job. Pure validation — no orchestration here (that's the
next step). The checks, in order:

    1. repo id is well-formed and safe   (allowlist — the security boundary)
    2. it exists on the Hugging Face Hub  (network)
    3. it is not gated/private
    4. its architecture is one vLLM can serve
    5. it fits a single a5000 (24 GB)

SECURITY: the repo id is untrusted input that LATER reaches a Slurm/sbatch
command line (when this is wired to the DCC). ``is_valid_repo_id`` is a strict
allowlist, and ``validate`` runs it FIRST — before any network call or
subprocess — mirroring the eval launcher's validate-before-spawn boundary.

The network fetch is injectable (``validate(..., fetch=...)``) so the rules are
fully unit-testable offline.
"""

from __future__ import annotations

import json
import urllib.request
import re
from dataclasses import dataclass
from typing import Callable, Optional

# A Hugging Face repo id is an optional "namespace/" followed by a name. Each
# segment starts alphanumeric and allows [A-Za-z0-9._-]; zero or one slash. This
# is an ALLOWLIST — spaces, shell metacharacters, '..', and extra slashes are
# rejected before the id can reach a subprocess.
_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)?$")
_MAX_REPO_ID_LEN = 96

# Architectures vLLM can serve. Curated starter subset — extend as the platform
# supports more (deliberately small for the MVP).
VLLM_SUPPORTED_ARCHITECTURES = frozenset({
    "LlamaForCausalLM", "Qwen2ForCausalLM", "Qwen2MoeForCausalLM",
    "MistralForCausalLM", "MixtralForCausalLM", "Phi3ForCausalLM",
    "GemmaForCausalLM", "Gemma2ForCausalLM", "FalconForCausalLM",
    "GPT2LMHeadModel", "GPTNeoXForCausalLM", "GPTBigCodeForCausalLM",
})

# Rough ceiling for one a5000 (24 GB): fp16 weights at ~2 bytes/param leave room
# for the KV cache / activations at roughly 9B params. Larger needs multi-GPU
# serving, which is out of the MVP.
MAX_PARAMS_A5000 = 9_000_000_000


@dataclass(frozen=True)
class ModelInfo:
    """The slice of HF Hub metadata the validator needs."""
    repo_id: str
    architectures: list[str]
    num_params: Optional[int]   # total parameter count if the Hub reports it
    gated: bool


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    error: Optional[str] = None
    info: Optional[ModelInfo] = None


def is_valid_repo_id(repo_id: str) -> bool:
    """True iff ``repo_id`` is a well-formed, safe Hugging Face repo id."""
    if not repo_id or len(repo_id) > _MAX_REPO_ID_LEN or ".." in repo_id:
        return False
    return bool(_REPO_ID_RE.match(repo_id))


def fetch_model_info(repo_id: str, *, timeout: float = 10.0) -> Optional[ModelInfo]:
    """Fetch model metadata from the HF Hub API; ``None`` if the repo is absent.

    Callers MUST validate ``repo_id`` first (it is interpolated into the URL)."""
    url = f"https://huggingface.co/api/models/{repo_id}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (validated id)
            data = json.loads(resp.read())
    except Exception:
        return None
    config = data.get("config") or {}
    safetensors = data.get("safetensors") or {}
    return ModelInfo(
        repo_id=repo_id,
        architectures=list(config.get("architectures") or []),
        num_params=safetensors.get("total"),
        gated=bool(data.get("gated")),
    )


def validate(
    repo_id: str,
    *,
    fetch: Callable[[str], Optional[ModelInfo]] = fetch_model_info,
    max_params: int = MAX_PARAMS_A5000,
) -> ValidationResult:
    """Decide whether we can evaluate ``repo_id`` before spawning any job.

    The allowlist runs FIRST (security), then the network fetch, then the
    gated / architecture / size checks. Returns a ``ValidationResult`` with a
    human-readable ``error`` on the first failing rule.
    """
    if not is_valid_repo_id(repo_id):
        return ValidationResult(
            False,
            "invalid repo id (expected 'name' or 'namespace/name', "
            "letters/digits/._- only)",
        )

    info = fetch(repo_id)
    if info is None:
        return ValidationResult(False, f"'{repo_id}' not found on the Hugging Face Hub")
    if info.gated:
        return ValidationResult(False, "model is gated/private; not supported in the MVP", info)
    if not info.architectures or not any(
        a in VLLM_SUPPORTED_ARCHITECTURES for a in info.architectures
    ):
        return ValidationResult(
            False,
            f"unsupported architecture {info.architectures or '[]'} "
            "(only vLLM-servable architectures are accepted)",
            info,
        )
    if info.num_params is not None and info.num_params > max_params:
        billions = info.num_params / 1e9
        return ValidationResult(
            False,
            f"model is too large (~{billions:.0f}B params) for a single a5000 "
            "(24 GB); multi-GPU serving is not in the MVP",
            info,
        )
    return ValidationResult(True, None, info)
