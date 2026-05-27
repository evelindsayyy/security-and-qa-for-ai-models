"""
download a small hugging face model for security scanning tests.

run this INSIDE the docker container (after docker compose run --rm scanner bash):
    python download_model.py

where files go:
    container: /models/distilbert-base-uncased/
    dgx host:  testing/security_scanning_tests/models/distilbert-base-uncased/
                 (same folder, bind-mounted — survives container exit)
"""

from pathlib import Path

from huggingface_hub import snapshot_download

# small public model (~260mb pytorch files) with both:
#   - pytorch_model.bin  (pickle — fickling)
#   - model.safetensors  (safe format — models can check this too)
REPO_ID = "distilbert-base-uncased"

# inside container this is /models/... which maps to ./models/ on dgx
LOCAL_DIR = Path("/models") / REPO_ID

# skip tensorflow/flax/msgpack junk — keeps download smaller
IGNORE_PATTERNS = ["*.msgpack", "*.h5", "flax_*", "tf_*"]


def main() -> None:
    # output dir parent should exist (compose creates ./models on host)
    LOCAL_DIR.parent.mkdir(parents=True, exist_ok=True)

    print(f"downloading {REPO_ID} ...")
    print(f"  -> {LOCAL_DIR}")
    print("(this writes to dgx disk via bind mount, not into the container layer)")

    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(LOCAL_DIR),
        ignore_patterns=IGNORE_PATTERNS,
    )

    print("\ndone. files downloaded:")
    for path in sorted(LOCAL_DIR.iterdir()):
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  {path.name:30s}  {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
