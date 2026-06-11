"""Garak runner for the safety pipeline."""

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


def _first_existing_report(base_dir: Path, preferred: Path) -> Path:
    if preferred.exists():
        return preferred
    for pattern in ("raw_garak_report*", "garak*"):
        for candidate in sorted(base_dir.glob(pattern)):
            if candidate.is_file() and candidate.suffix.lower() in {".json", ".jsonl"}:
                return candidate
    return preferred


def run_garak(
    model_id: str,
    *,
    target: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> ToolRunResult:
    """Render a Garak config, run Garak when available, and persist the result."""
    target_config = resolve_target(model_id) if target is None else dict(target)
    base_dir = output_dir or Path("safety/garak_testing/output") / _slugify(model_id)
    base_dir.mkdir(parents=True, exist_ok=True)

    config_path = base_dir / "garak_runtime.yaml"
    report_path = base_dir / "raw_garak_report.json"
    metadata_path = base_dir / "garak_run_metadata.json"
    template_path = Path(__file__).with_name("templates") / "garak_base.yaml"
    gateway_model_id = target_config.get("model_id", model_id)

    rendered = _render_template(
        template_path,
        {
            "model_id": gateway_model_id,
            "provider_id": target_config.get("provider_id", "openai:chat:GPT 4.1 Mini"),
            "label": target_config.get("label", gateway_model_id),
            "api_base_url": target_config.get("api_base_url", "https://litellm.oit.duke.edu/v1"),
            "api_key_env": target_config.get("api_key_env", "OPENAI_API_KEY"),
            "temperature": target_config.get("temperature", 0),
            "max_tokens": target_config.get("max_tokens", 300),
            "report_path": str(report_path),
        },
    )
    config_path.write_text(rendered, encoding="utf-8")

    garak_cmd = shutil.which("garak")
    if garak_cmd:
        cmd = [
            garak_cmd,
            "-c",
            str(config_path),
            "--report_prefix",
            str(base_dir / "raw_garak_report"),
        ]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
            report_path = _first_existing_report(base_dir, report_path)
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
                    "reason": "garak executable is not available in PATH",
                    "config_path": str(config_path),
                    "raw_output_path": str(report_path),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        status = "skipped"
        notes = ["garak executable is not available in PATH"]

    return ToolRunResult(
        tool_name="garak",
        model_id=gateway_model_id,
        status=status,
        output_dir=str(base_dir),
        config_path=str(config_path),
        command=[garak_cmd] if garak_cmd else None,
        metadata={
            "notes": notes,
            "target": target_config,
            "report_path": str(report_path),
            "metadata_path": str(metadata_path),
        },
    )
