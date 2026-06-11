"""Main orchestration layer for the safety red-teaming pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from safety.garak_runner import run_garak
from safety.promptfoo_runner import run_promptfoo
from safety.schemas import SafetyRunResult, ToolRunResult
from safety.targets import resolve_target


DEFAULT_OUTPUT_ROOT = Path("safety/output")


def _output_dir(model_id: str, output_dir: Path | None = None) -> Path:
    if output_dir is not None:
        return output_dir / model_id
    return DEFAULT_OUTPUT_ROOT / model_id


def _write_summary(result: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return summary_path


def scan_model(model_id: str, *, output_dir: Path | None = None) -> dict[str, Any]:
    """Run the safety pipeline for one model alias.

    The current implementation uses the scanner-style split:
      - resolve target
      - run tool-specific wrappers
      - write a summary JSON for downstream scoring
    """
    target = resolve_target(model_id)
    out_dir = _output_dir(model_id, output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    garak = run_garak(model_id, target=target, output_dir=out_dir)
    promptfoo = run_promptfoo(model_id, target=target, output_dir=out_dir)

    summary = {
        "model_id": model_id,
        "target": target,
        "garak": {
            "status": garak.status,
            "output_dir": garak.output_dir,
            "config_path": garak.config_path,
        },
        "promptfoo": {
            "status": promptfoo.status,
            "output_dir": promptfoo.output_dir,
            "config_path": promptfoo.config_path,
        },
        "combined_output": None,
    }

    # If the existing safety scorer is present, invoke it as the normalization layer.
    garak_path = Path(garak.output_dir) / "garak_report.json"
    promptfoo_path = Path(promptfoo.output_dir) / "promptfoo_report.json"
    if garak_path.exists() and promptfoo_path.exists():
        combined_path = out_dir / "combined_safety_result.json"
        cmd = [
            sys.executable,
            "safety/safety_score.py",
            "--garak",
            str(garak_path),
            "--promptfoo",
            str(promptfoo_path),
            "-o",
            str(combined_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            summary["notes"] = [f"Scoring step skipped: {exc}"]
        else:
            summary["combined_output"] = str(combined_path)

    summary_path = _write_summary(summary, out_dir)
    summary["summary_path"] = str(summary_path)
    return summary
