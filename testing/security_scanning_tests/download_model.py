"""download distilbert to /models/ — run inside container after compose up."""

from pathlib import Path

from huggingface_hub import snapshot_download

REPO_ID = "distilbert-base-uncased"
LOCAL_DIR = Path("/models") / REPO_ID


def main() -> None:
    LOCAL_DIR.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {REPO_ID} to {LOCAL_DIR} ...")

    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(LOCAL_DIR),
        ignore_patterns=["*.msgpack", "*.h5", "flax_*", "tf_*"],
    )

    print("done.")


if __name__ == "__main__":
    main()
