"""download hf repo weights to MODELS_ROOT."""

from __future__ import annotations

from huggingface_hub import snapshot_download

from scanner.paths import model_dir


def download_model(model_id: str) -> Path:
    target = model_dir(model_id)
    target.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=model_id,
        local_dir=str(target),
        ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*"],
    )
    return target
