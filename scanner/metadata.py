"""hf hub metadata only — no weight download."""

from __future__ import annotations

from typing import Any

from huggingface_hub import HfApi

from scanner.paths import PICKLE_WEIGHT_NAMES


def build_metadata_report(model_id: str) -> dict[str, Any]:
    api = HfApi()
    info = api.model_info(repo_id=model_id)
    files = api.list_repo_files(repo_id=model_id)

    siblings = []
    total_size = 0
    for s in info.siblings or []:
        size = s.size or 0
        total_size += size
        siblings.append({"rfilename": s.rfilename, "size": size})

    lower_files = {f.lower() for f in files}
    has_pickle = any(name in files for name in PICKLE_WEIGHT_NAMES)
    has_safetensors = any(f.endswith(".safetensors") for f in files)
    has_requirements = "requirements.txt" in lower_files or "requirements-dev.txt" in lower_files

    return {
        "model_id": model_id,
        "sha": info.sha,
        "private": info.private,
        "pipeline_tag": info.pipeline_tag,
        "tags": list(info.tags or []),
        "library_name": info.library_name,
        "file_count": len(files),
        "files": files,
        "siblings": siblings,
        "total_size_bytes": total_size,
        "has_pickle_weights": has_pickle,
        "has_safetensors": has_safetensors,
        "has_requirements_txt": has_requirements,
        "scan_hints": {
            "modelscan_needs_download": has_pickle or has_safetensors,
            "fickling_needs_download": has_pickle,
            "dependency_scan_possible": has_requirements,
        },
    }
