"""path helpers — hf weights and scan json live under scanner/models and scanner/output."""

from __future__ import annotations

import json
import os
from pathlib import Path

# package dir: scanner/ — works on host and in docker (/app/scanner)
_PKG_ROOT = Path(__file__).resolve().parent

# optional override (e.g. old compose used /models mount); default is repo-local under scanner/
MODELS_ROOT = Path(os.environ.get("MODELS_ROOT", _PKG_ROOT / "models"))
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", _PKG_ROOT / "output"))

DEFAULT_MODEL_ID = "distilbert-base-uncased"

PICKLE_WEIGHT_NAMES = ("pytorch_model.bin", "model.bin", "pytorch_model.pt", "model.pt")


def safe_dir_name(model_id: str) -> str:
    return model_id.replace("/", "--")


def get_model_id() -> str:
    return os.environ.get("MODEL_ID", DEFAULT_MODEL_ID)


def model_dir(model_id: str) -> Path:
    return MODELS_ROOT / safe_dir_name(model_id)


def output_dir(model_id: str) -> Path:
    return OUTPUT_ROOT / safe_dir_name(model_id)


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
