"""Promptfoo runner for the safety pipeline."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from safety.schemas import ToolRunResult
from safety.targets import resolve_target


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "target"


def _render_template(template_path: Path, values: dict[str, Any]) -> str:
    text = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def run_promptfoo(
    model_id: str,
    *,
    target: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> ToolRunResult:
    """Render a Promptfoo config, run Promptfoo when available, and persist the result."""
    target_config = resolve_target(model_id) if target is None else dict(target)
    base_dir = output_dir or Path("safety/promptfoo_testing/output") / _slugify(model_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    config_path = base_dir / "promptfoo_runtime.yaml"
    report_path = base_dir / "raw_promptfoo_report.json"
    metadata_path = base_dir / "promptfoo_run_metadata.json"
    template_path = Path(__file__).with_name("templates") / "promptfoo_base.yaml"

    rendered = _render_template(
        template_path,
        {
            "model_id": model_id,
            "provider_id": target_config.get("provider_id", "openai:chat:GPT 4.1 Mini"),
            "label": target_config.get("label", model_id),
            "api_base_url": target_config.get("api_base_url", "https://litellm.oit.duke.edu/v1"),
            "api_key_env": target_config.get("api_key_env", "OPENAI_API_KEY"),
            "temperature": target_config.get("temperature", 0),
            "max_tokens": target_config.get("max_tokens", 300),
        },
    )
    config_path.write_text(rendered, encoding="utf-8")

    promptfoo_cmd = shutil.which("promptfoo")
    if promptfoo_cmd:
        cmd = [promptfoo_cmd, "eval", "--config", str(config_path), "--output", str(report_path)]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
            metadata_path.write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "command": cmd,
                        "raw_output_path": str(report_path),
                        "stdout": completed.stdout,
                        "stderr": completed.stderr,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            status = "ok"
            notes = []
        except subprocess.CalledProcessError as exc:
            metadata_path.write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "command": cmd,
                        "raw_output_path": str(report_path),
                        "returncode": exc.returncode,
                        "stdout": exc.stdout,
                        "stderr": exc.stderr,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            status = "failed"
            notes = [str(exc)]
    else:
        metadata_path.write_text(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "promptfoo executable is not available in PATH",
                    "config_path": str(config_path),
                    "raw_output_path": str(report_path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        status = "skipped"
        notes = ["promptfoo executable is not available in PATH"]

    return ToolRunResult(
        tool_name="promptfoo",
        model_id=model_id,
        status=status,
        output_dir=str(base_dir),
        config_path=str(config_path),
        command=[promptfoo_cmd] if promptfoo_cmd else None,
        metadata={
            "notes": notes,
            "target": target_config,
            "report_path": str(report_path),
            "metadata_path": str(metadata_path),
        },
    )
