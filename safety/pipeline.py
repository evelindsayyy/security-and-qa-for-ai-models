"""Main orchestration layer for the safety red-teaming pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from safety.garak_runner import run_garak
from safety.promptfoo_runner import run_promptfoo
from safety.safety_score import score_garak_file, score_promptfoo_file
from safety.schemas import ToolRunResult
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


def _deployment_context(target: dict[str, Any]) -> dict[str, Any]:
    """Copy non-secret runtime context into safety_runs.deployment_context."""
    keys = (
        "provider_id",
        "model_id",
        "label",
        "api_base_url",
        "api_key_env",
        "temperature",
        "max_tokens",
        "description",
    )
    return {key: target[key] for key in keys if key in target}


def _tool_summary(result: ToolRunResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "output_dir": result.output_dir,
        "config_path": result.config_path,
        "raw_output": result.metadata.get("report_path"),
        "run_metadata": result.metadata.get("metadata_path"),
        "safety_result": None,
    }


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

    garak_dir = out_dir / "garak"
    promptfoo_dir = out_dir / "promptfoo"

    garak = run_garak(model_id, target=target, output_dir=garak_dir)
    promptfoo = run_promptfoo(model_id, target=target, output_dir=promptfoo_dir)

    summary = {
        "model_id": model_id,
        "target": target,
        "garak": _tool_summary(garak),
        "promptfoo": _tool_summary(promptfoo),
        "safety_results": {},
        "notes": [],
    }

    context = _deployment_context(target)

    garak_raw_output = summary["garak"]["raw_output"]
    garak_path = Path(garak_raw_output) if garak_raw_output else None
    if garak_path and garak_path.is_file():
        garak_result_path = garak_dir / "garak_safety_result.json"
        try:
            score_garak_file(
                garak_path,
                garak_result_path,
                model_id=model_id,
                deployment_context=context,
            )
        except (OSError, ValueError) as exc:
            summary["notes"].append(f"Garak scoring skipped: {exc}")
        else:
            summary["garak"]["safety_result"] = str(garak_result_path)
            summary["safety_results"]["garak"] = str(garak_result_path)
    else:
        summary["notes"].append(f"Garak raw output not found: {garak_raw_output or 'unset'}")

    promptfoo_raw_output = summary["promptfoo"]["raw_output"]
    promptfoo_path = Path(promptfoo_raw_output) if promptfoo_raw_output else None
    if promptfoo_path and promptfoo_path.is_file():
        promptfoo_result_path = promptfoo_dir / "promptfoo_safety_result.json"
        try:
            score_promptfoo_file(
                promptfoo_path,
                promptfoo_result_path,
                model_id=model_id,
                deployment_context=context,
            )
        except (OSError, ValueError) as exc:
            summary["notes"].append(f"Promptfoo scoring skipped: {exc}")
        else:
            summary["promptfoo"]["safety_result"] = str(promptfoo_result_path)
            summary["safety_results"]["promptfoo"] = str(promptfoo_result_path)
    else:
        summary["notes"].append(f"Promptfoo raw output not found: {promptfoo_raw_output or 'unset'}")

    summary_path = _write_summary(summary, out_dir)
    summary["summary_path"] = str(summary_path)
    return summary
