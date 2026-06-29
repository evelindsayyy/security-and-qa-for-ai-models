"""Validate Garak JSONL reports for Duke probe-set completeness."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from dbutils.env import REPO_ROOT

CONFIG_FILE = REPO_ROOT / "safety" / "garak" / "garak_duke.yaml"


def _default_probe_spec() -> str:
    if not CONFIG_FILE.is_file():
        return ""
    data = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    return str((data.get("plugins") or {}).get("probe_spec") or "")


DEFAULT_PROBE_SPEC = _default_probe_spec()


def probe_module(name: str) -> str:
    """``dan.Dan_11_0`` → ``dan``; ``encoding.InjectHex`` → ``encoding``."""
    return name.split(".")[0] if "." in name else name


def expected_module_count(probe_spec: str) -> int:
    """Unique module count for a comma-separated probe_spec (dan sub-probes → one)."""
    modules = {
        probe_module(part.strip())
        for part in probe_spec.split(",")
        if part.strip()
    }
    return len(modules)


def _load_rows(report_path: Path) -> list[dict]:
    rows: list[dict] = []
    with report_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def analyze_report(report_path: Path) -> dict:
    """Summarize a garak-duke report JSONL without exporting findings."""
    rows = _load_rows(report_path)
    eval_modules: set[str] = set()
    for row in rows:
        if row.get("entry_type") != "eval":
            continue
        probe = str(row.get("probe") or "")
        if probe:
            eval_modules.add(probe_module(probe))

    has_completion = any(r.get("entry_type") == "completion" for r in rows)
    has_digest = any(r.get("entry_type") == "digest" for r in rows)
    return {
        "row_count": len(rows),
        "completed_modules": sorted(eval_modules),
        "completed_module_count": len(eval_modules),
        "has_completion": has_completion,
        "has_digest": has_digest,
    }


def validate_report(
    report_path: Path,
    *,
    probe_spec: str | None = None,
) -> tuple[bool, str, dict]:
    """Return (ok, error_message, analysis dict).

    *ok* when the report has a ``completion`` entry and at least the expected
    number of distinct eval modules for *probe_spec* (defaults to Duke 14 yaml).
    """
    spec = probe_spec or DEFAULT_PROBE_SPEC
    if not spec:
        return False, "probe_spec missing for validation", {}

    expected = expected_module_count(spec)
    try:
        analysis = analyze_report(report_path)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"could not read garak report: {exc}", {}

    count = analysis["completed_module_count"]
    if not analysis["has_completion"]:
        return (
            False,
            f"garak report incomplete: {count}/{expected} modules, no completion entry",
            analysis,
        )
    if count < expected:
        return (
            False,
            f"garak report incomplete: {count}/{expected} modules ran",
            analysis,
        )
    return True, "", analysis
