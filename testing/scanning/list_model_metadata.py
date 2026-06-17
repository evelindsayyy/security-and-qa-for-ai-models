"""
list huggingface model metadata + file list — no weight download.

why separate from download_model.py:
  - snapshot_download() pulls gigabytes we don't need for inventory / nutrition label
  - many checks only need the file manifest first (then selective small-file fetch)

when you need actual bytes vs metadata only:
  | task                              | metadata only | full download      |
  |-----------------------------------|---------------|--------------------|
  | repo inventory, sizes, tags       | yes           | no                 |
  | see if requirements.txt exists    | yes (list)    | no                 |
  | modelscan / fickling on pickles   | no            | yes (.bin on disk) |
  | trufflehog / bandit on file text  | no            | yes                |
  | dep scan from requirements.txt    | list + optional single-file hf_hub_download | full tree ok |

week 4 middle ground: hf_hub_download(repo_id, filename="requirements.txt") — one small file, no weights.
"""

from __future__ import annotations

import json

from huggingface_hub import HfApi

from scan_helpers import dump_json, get_model_id, output_dir, safe_dir_name

# filenames that imply pickle-based weights (same idea as scan_helpers)
PICKLE_WEIGHT_NAMES = ("pytorch_model.bin", "model.bin", "pytorch_model.pt", "model.pt")
SAFETENSORS_MARKERS = (".safetensors",)


def build_metadata_report(model_id: str) -> dict:
    api = HfApi()

    # model_info = card metadata, tags, sha, sibling list with sizes (no download)
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
        # quick hint for which scan tools apply without downloading
        "scan_hints": {
            "modelscan_needs_download": has_pickle or has_safetensors,
            "fickling_needs_download": has_pickle,
            "dependency_scan_possible": has_requirements,
        },
    }


def main() -> None:
    model_id = get_model_id()
    print(f"fetching metadata for {model_id} (no weights) ...")

    report = build_metadata_report(model_id)

    # print summary to stdout for quick inspection in the container
    print(json.dumps(
        {k: report[k] for k in ("model_id", "sha", "file_count", "total_size_bytes",
                               "has_pickle_weights", "has_safetensors", "scan_hints")},
        indent=2,
    ))

    out_path = output_dir(model_id) / "metadata.json"
    dump_json(out_path, report)
    print(f"full report -> {out_path}")
    print(f"safe dir name on disk: {safe_dir_name(model_id)}")


if __name__ == "__main__":
    main()
