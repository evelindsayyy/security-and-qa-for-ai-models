"""HF repos to scan for open-weight Duke gateway models (non-gated mirrors).

Meta official repos are often gated even with HF_TOKEN. These community mirrors
are the intended scan targets; verify access on the VM before bulk runs:

  huggingface-cli repo info <repo>

Catalog rollup uses this map to attach scan results to the gateway model slug.
"""

from __future__ import annotations

from frontend.model_identity import gateway_slug

# Gateway LiteLLM id -> public HF repo id (update when mirrors change).
GATEWAY_HF_SCAN_REPOS: dict[str, str] = {
    "Llama 3.3": "NousResearch/Meta-Llama-3.3-70B-Instruct",
    # Quantized fallback if 70B is too large for VM disk:
    # "Llama 3.3": "unsloth/Meta-Llama-3.3-70B-Instruct-GGUF",
    "Llama 4 Maverick": "unsloth/Llama-4-Maverick-17B-128E-Instruct",
    "Llama 4 Scout": "unsloth/Llama-4-Scout-17B-16E-Instruct",
}

def gateway_slug_for_hf_repo(hf_repo: str) -> str | None:
    """Return gateway catalog slug when this HF repo is a known OSS gateway mirror."""
    for gateway_id, repo in GATEWAY_HF_SCAN_REPOS.items():
        if repo == hf_repo:
            return gateway_slug(gateway_id)
    return None
