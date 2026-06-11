"""Simple result models for the safety red-teaming pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolRunResult:
    """Description of a single tool execution result."""

    tool_name: str
    model_id: str
    status: str
    output_dir: str
    config_path: str | None = None
    command: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SafetyRunResult:
    """Normalized summary returned by the safety pipeline."""

    model_id: str
    target: dict[str, Any]
    garak: ToolRunResult | None
    promptfoo: ToolRunResult | None
    combined_output: str | None = None
    notes: list[str] = field(default_factory=list)
