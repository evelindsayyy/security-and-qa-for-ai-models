"""
Download a Hugging Face model repository into ``MODELS_ROOT``.

Used by the full scan pipeline when weights are not already on disk.
Does not run any security tools — see ``pipeline.scan_model`` for that.

Requires ``HF_TOKEN`` (or ``HUGGINGFACE_TOKEN``) in the environment for gated repos.
"""

from __future__ import annotations

from pathlib import Path

from huggingface_hub import snapshot_download

from scanner.paths import model_dir


def download_model(model_id: str) -> Path:
    """
    Fetch all repo files for ``model_id`` into ``models/<slug>/``.

    Skips some alternate-framework blobs (msgpack, h5, flax, tf) to save space;
    Track A scanners target PyTorch/safetensors/onnx artifacts on typical HF repos.

    Returns the model directory path (created if missing).
    """
    target = model_dir(model_id)
    target.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=model_id,
        local_dir=str(target),
        ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*"],
    )
    return target
