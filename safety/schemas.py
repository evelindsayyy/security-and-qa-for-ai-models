"""Contracts for Track A safety artifacts.

``SafetyResult`` is the JSON bridge to ``docs/data-model.md``:
``run`` maps to one ``safety_runs`` row, and each ``finding`` maps to one
``safety_findings`` row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "safety_result_v1"


class SafetyCategory(str, Enum):
    """Allowed Track A finding categories."""

    jailbreak = "jailbreak"
    toxicity = "toxicity"
    policy = "policy"
    leakage = "leakage"


class SafetySource(str, Enum):
    """Tool/source values accepted by ``safety_findings.source``."""

    garak = "garak"
    promptfoo = "promptfoo"
    duke_probe = "duke_probe"


class SafetySeverity(str, Enum):
    """Severity labels used by safety findings."""

    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class SafetyFinding(BaseModel):
    """One normalized UI finding, matching ``safety_findings``."""

    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    safety_run_id: str
    category: SafetyCategory
    source: SafetySource
    passed: bool
    severity: SafetySeverity
    title: str
    description: str
    probe_id: str


class SafetyRun(BaseModel):
    """One tool-specific red-team run, matching ``safety_runs``."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    gateway_model_id: str
    status: str
    deployment_context: dict[str, Any] = Field(default_factory=dict)
    probe_suite: str
    summary_pass_rate: float
    tool_results: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    completed_at: str


class SafetyResult(BaseModel):
    """Full JSON artifact for one tool-specific safety run."""

    schema_version: str = SCHEMA_VERSION
    run: SafetyRun
    findings: list[SafetyFinding] = Field(default_factory=list)


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
    garak_score_output: str | None = None
    promptfoo_score_output: str | None = None
    notes: list[str] = field(default_factory=list)
