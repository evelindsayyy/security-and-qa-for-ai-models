"""
Filesystem layout for downloaded weights and scan artifacts.

All paths are rooted under ``scanner/models`` and ``scanner/output`` by default.
Hub ids like ``BAAI/bge-small-en-v1.5`` become directory slugs ``BAAI--bge-small-en-v1.5``.

Override roots in Docker or CI via ``MODELS_ROOT`` / ``OUTPUT_ROOT`` env vars.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Package directory (scanner/) — stable on host and in Docker (/app/scanner).
_PKG_ROOT = Path(__file__).resolve().parent

# Where snapshot_download writes weights; override for alternate mounts.
MODELS_ROOT = Path(os.environ.get("MODELS_ROOT", _PKG_ROOT / "models"))
# Where scan_result.json and per-tool debug reports are written.
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", _PKG_ROOT / "output"))

# Default when MODEL_ID env is set without CLI args (compose convenience).
DEFAULT_MODEL_ID = "distilbert-base-uncased"

# Canonical Hugging Face weight filenames that imply pickle/pytorch serialization.
PICKLE_WEIGHT_NAMES = ("pytorch_model.bin", "model.bin", "pytorch_model.pt", "model.pt")


def safe_dir_name(model_id: str) -> str:
    """Turn ``org/model`` into a single path segment safe on all filesystems."""
    return model_id.replace("/", "--")


def get_model_id() -> str:
    """Resolve model id from ``MODEL_ID`` env or package default."""
    return os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)


def model_dir(model_id: str) -> Path:
    """Local directory containing a full or partial HF snapshot for ``model_id``."""
    return MODELS_ROOT / safe_dir_name(model_id)


def output_dir(model_id: str) -> Path:
    """Per-model output folder (scan_result.json, tool reports, spikes)."""
    return OUTPUT_ROOT / safe_dir_name(model_id)


def dump_json(path: Path, data: dict) -> None:
    """Write indented JSON, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
