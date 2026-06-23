#!/usr/bin/env python3
"""
Garak launcher — auto-selects the right generator profile for the target model.

Usage (inside the Docker container or with garak on PATH):
    python run_garak.py <model-name> [extra garak args...]

Examples:
    python run_garak.py "GPT 4.1 Mini"
    python run_garak.py "gpt-5.5"
    python run_garak.py "gpt-5.4-pro" --probe_spec dan.Dan_11_0

Model name is forwarded to garak as -n; it is also used to pick the generator
profile from _generator_profiles in garak_duke.yaml:
  - openai5  →  gpt-5.x, o3, o4-mini  (uses suppressed_params + max_completion_tokens)
  - standard →  everything else        (uses temperature / max_tokens)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

CONFIG_FILE = Path(__file__).parent / "garak_duke.yaml"

# Matches GPT-5 series and o3/o4-family model names (case-insensitive).
_OPENAI5 = re.compile(r"(?i)^(gpt-5|o[34][-\s]|o[34]$)")

# HuggingFace models used by garak detectors. Downloaded once, cached to disk.
# Eager prefetch prevents mid-run crashes when a probe first triggers a lazy load.
_HF_DETECTOR_MODELS = [
    "garak-llm/roberta_toxicity_classifier",        # latentinjection + unsafe_content detectors
    "garak-llm/refutation_detector_distilbert",     # misleading detector
    "garak-llm/attackgeneration-toxicity_gpt2",     # atkgen attack generator
]


def _prefetch_hf_models() -> None:
    """Download required detector models before the run starts."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[run_garak] huggingface_hub not available — skipping prefetch", flush=True)
        return

    for repo_id in _HF_DETECTOR_MODELS:
        print(f"[run_garak] prefetch {repo_id} ...", end=" ", flush=True)
        try:
            snapshot_download(repo_id, local_files_only=False)
            print("ok", flush=True)
        except Exception as exc:
            print(f"FAILED ({exc})", flush=True)
            print(
                f"[run_garak] WARNING: could not download {repo_id}. "
                "Probes that rely on this detector will fail.",
                flush=True,
            )


def _pick_profile(model_name: str) -> str:
    return "openai5" if _OPENAI5.match(model_name.strip()) else "standard"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("model_name")
    parser.add_argument("--report-dir", default=None)
    args, extra_args = parser.parse_known_args()

    model_name = args.model_name

    _prefetch_hf_models()

    with CONFIG_FILE.open() as f:
        cfg = yaml.safe_load(f)

    profile = _pick_profile(model_name)
    generator_cfg = cfg["_generator_profiles"][profile]

    cfg["plugins"]["generators"]["openai"]["OpenAICompatible"] = generator_cfg
    cfg.pop("_generator_profiles", None)

    if args.report_dir:
        cfg.setdefault("reporting", {})["report_dir"] = args.report_dir

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", dir=CONFIG_FILE.parent, delete=False
    ) as tmp:
        yaml.dump(cfg, tmp, default_flow_style=False, allow_unicode=True)
        tmp_path = Path(tmp.name)

    print(f"[run_garak] model={model_name!r}  profile={profile}  config={tmp_path.name}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "garak", "--config", tmp_path.name, "-n", model_name, *extra_args],
            check=False,
        )
        return result.returncode
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
