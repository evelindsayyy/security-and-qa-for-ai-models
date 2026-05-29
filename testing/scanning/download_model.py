"""download a hugging face model to /models/ — set MODEL_ID env var to change model."""

from huggingface_hub import snapshot_download

from scan_helpers import get_model_dir, get_model_id


def main() -> None:
    model_id = get_model_id()
    model_dir = get_model_dir(model_id)
    # create target dir — needs write access on /models (see readme if permission denied)
    model_dir.mkdir(parents=True, exist_ok=True)

    print(f"MODEL_ID={model_id}")
    print(f"downloading to {model_dir} ...")

    snapshot_download(
        repo_id=model_id,
        local_dir=str(model_dir),
        ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*"],
    )

    print("done.")


if __name__ == "__main__":
    main()
