#!/usr/bin/env python3
"""
Garak launcher — auto-selects the right generator profile for the target model.

Usage (inside the Docker container or with garak on PATH):
    python run_garak.py <model-name> [extra garak args...]

Examples:
    python run_garak.py "GPT 4.1 Mini"
    python run_garak.py "gpt-5.5"
    python run_garak.py "gpt-5.4-pro" -p dan.Dan_11_0

Model name is forwarded to garak as -n; it is also used to pick the generator
profile from _generator_profiles in garak_duke.yaml:
  - openai5  →  gpt-5.x, o3, o4-mini  (uses suppressed_params + max_completion_tokens)
  - standard →  everything else        (uses temperature / max_tokens)

Probe list lives in garak_duke.yaml plugins.probe_spec (single source of truth).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from dbutils.env import REPO_ROOT
from safety.garak.report_validation import validate_report

CONFIG_FILE = Path(__file__).parent / "garak_duke.yaml"

# Matches GPT-5 series and o3/o4-family model names (case-insensitive).
_OPENAI5 = re.compile(r"(?i)^(gpt-5|o[34][-\s]|o[34]$)")

# HuggingFace models used by garak detectors. Downloaded once, cached to disk.
_HF_DETECTOR_MODELS = [
    "garak-llm/roberta_toxicity_classifier",
    "garak-llm/refutation_detector_distilbert",
    "garak-llm/attackgeneration-toxicity_gpt2",
]


def _resolve_probe_spec(yaml_spec: str, extra_args: list[str]) -> str:
    for i, arg in enumerate(extra_args):
        if arg in ("-p", "--probes") and i + 1 < len(extra_args):
            return extra_args[i + 1]
    return yaml_spec


def _validate_probe_spec(probe_spec: str) -> tuple[int, int]:
    """Return (module_count, sub_probe_count) or exit 1 on invalid/inactive probes."""
    from garak import _config

    names, rejected = _config.parse_plugin_spec(probe_spec, "probes")
    if rejected:
        print(
            f"[run_garak] ERROR: invalid/inactive probes: {','.join(rejected)}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not names:
        print("[run_garak] ERROR: probe_spec resolved to zero probes", file=sys.stderr)
        raise SystemExit(1)
    return len(probe_spec.split(",")), len(names)


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


def _prefetch_toxic_detector() -> None:
    """Fail fast if ToxicCommentModel cannot load (needs USER/HOME in container)."""
    print("[run_garak] preflight ToxicCommentModel ...", end=" ", flush=True)
    try:
        from garak.detectors.unsafe_content import ToxicCommentModel

        ToxicCommentModel()
    except Exception as exc:
        print("FAILED", flush=True)
        print(
            f"[run_garak] ERROR: ToxicCommentModel preflight failed: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    print("ok", flush=True)


def _pick_profile(model_name: str) -> str:
    return "openai5" if _OPENAI5.match(model_name.strip()) else "standard"


def _probe_cli_args(extra_args: list[str], probe_spec: str) -> list[str]:
    """Pass probes via CLI -p (reliable across garak 0.14/0.15 yaml quirks)."""
    if any(a in ("-p", "--probes") for a in extra_args):
        return extra_args
    return ["-p", probe_spec, *extra_args]


def _write_temp_config(cfg: dict) -> Path:
    """Write merged config outside the repo tree."""
    fd, path = tempfile.mkstemp(suffix=".yaml", prefix="garak-duke-", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.dump(cfg, fh, default_flow_style=False, allow_unicode=True)
    except Exception:
        os.close(fd)
        Path(path).unlink(missing_ok=True)
        raise
    return Path(path)


def _exit_status(report_dir: str | None, returncode: int, probe_spec: str) -> int:
    if returncode != 0:
        return returncode
    if not report_dir:
        return 0
    reports = sorted(Path(report_dir).glob("garak-duke*.report.jsonl"))
    if not reports:
        print(
            "[run_garak] ERROR: garak finished but no garak-duke*.report.jsonl "
            f"in {report_dir}",
            file=sys.stderr,
        )
        return 1
    ok, err, _analysis = validate_report(reports[-1], probe_spec=probe_spec)
    if not ok:
        print(f"[run_garak] ERROR: {err}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("model_name")
    parser.add_argument("--report-dir", default=None)
    args, extra_args = parser.parse_known_args()

    model_name = args.model_name

    with CONFIG_FILE.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    yaml_spec = (cfg.get("plugins") or {}).get("probe_spec", "")
    if not yaml_spec:
        print("[run_garak] ERROR: plugins.probe_spec missing in garak_duke.yaml", file=sys.stderr)
        return 1

    probe_spec = _resolve_probe_spec(yaml_spec, extra_args)
    module_count, sub_probe_count = _validate_probe_spec(probe_spec)

    _prefetch_hf_models()
    _prefetch_toxic_detector()

    profile = _pick_profile(model_name)
    generator_cfg = cfg["_generator_profiles"][profile]

    cfg["plugins"]["generators"]["openai"]["OpenAICompatible"] = generator_cfg
    cfg.pop("_generator_profiles", None)

    if args.report_dir:
        report_dir = str(Path(args.report_dir).resolve())
        cfg.setdefault("reporting", {})["report_dir"] = report_dir
    else:
        report_dir = None

    tmp_path = _write_temp_config(cfg)
    config_path = str(tmp_path.resolve())
    print(
        f"[run_garak] model={model_name!r}  profile={profile}  "
        f"probes={module_count} modules, {sub_probe_count} sub-probes",
        flush=True,
    )

    garak_args = _probe_cli_args(extra_args, probe_spec)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "garak", "--config", config_path, "-n", model_name, *garak_args],
            check=False,
        )
        return _exit_status(report_dir, result.returncode, probe_spec)
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
