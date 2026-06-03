"""
Classify files in a downloaded Hugging Face model directory.

Runs before scanners so ``pipeline`` and ``risk_scorer`` know:
  - whether Fickling applies (any pickle-family weight present)
  - whether the repo is safetensors-only (Fickling omitted from label logic)
  - what file categories exist for ``scan_metadata.file_formats``

Does not perform security analysis — only inventory by extension/name patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from scanner.paths import PICKLE_WEIGHT_NAMES
from scanner.pickle_scan import _PICKLE_FAMILY_SUFFIXES

# Source files in repos — tracked for coverage, not sent to ModelAudit as weights.
CODE_EXTENSIONS = {".py", ".cpp", ".c", ".h", ".cu", ".rs", ".go"}
CONFIG_NAMES = {
    "config.json",
    "generation_config.json",
    "tokenizer_config.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
}


class FileFormatSummary(BaseModel):
    """
    Aggregated file inventory for one model directory.

    ``by_category`` maps category → relative paths; ``flags`` drive pipeline branches.
    """

    by_category: dict[str, list[str]] = Field(default_factory=dict)
    flags: dict[str, bool] = Field(default_factory=dict)
    file_count: int = 0


def _is_pickle_family_path(rel_path: str) -> bool:
    """True if path looks like a PyTorch/pickle weight (see also ``pickle_scan``)."""
    name = Path(rel_path).name
    lower = rel_path.lower()
    if name in PICKLE_WEIGHT_NAMES:
        return True
    return lower.endswith(_PICKLE_FAMILY_SUFFIXES)


def _category_for_file(rel_path: str) -> str:
    """Assign one category label per repo-relative path."""
    name = Path(rel_path).name
    lower = rel_path.lower()

    if _is_pickle_family_path(rel_path):
        return "pickle"
    if lower.endswith(".safetensors"):
        return "safetensors"
    if lower.endswith(".onnx") or lower.endswith(".onnx_data"):
        return "onnx"
    if name in CONFIG_NAMES or lower.endswith(".json"):
        return "config"
    if Path(lower).suffix in CODE_EXTENSIONS:
        return "code"
    return "other"


def summarize(model_dir: Path) -> FileFormatSummary:
    """
    Walk ``model_dir`` (skip ``.cache``) and build category lists + boolean flags.

    Raises:
        FileNotFoundError: if ``model_dir`` is missing (caller should download first).
    """
    if not model_dir.is_dir():
        raise FileNotFoundError(f"model dir missing: {model_dir}")

    by_category: dict[str, list[str]] = {
        "safetensors": [],
        "pickle": [],
        "onnx": [],
        "config": [],
        "code": [],
        "other": [],
    }

    for path in sorted(model_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(model_dir))
        if rel.startswith(".cache"):
            continue
        cat = _category_for_file(rel)
        by_category.setdefault(cat, []).append(rel)

    has_safetensors = len(by_category["safetensors"]) > 0
    has_pickle = len(by_category["pickle"]) > 0
    safetensors_only = has_safetensors and not has_pickle

    flags = {
        "has_safetensors": has_safetensors,
        "has_pickle_weights": has_pickle,
        "has_onnx": len(by_category["onnx"]) > 0,
        "safetensors_only": safetensors_only,
        "fickling_applicable": has_pickle,
    }

    return FileFormatSummary(
        by_category={k: v for k, v in by_category.items() if v},
        flags=flags,
        file_count=sum(len(v) for v in by_category.values()),
    )


def summary_to_metadata_dict(summary: FileFormatSummary) -> dict[str, Any]:
    """Serialize ``FileFormatSummary`` into ``scan_metadata.file_formats``."""
    return summary.model_dump()
