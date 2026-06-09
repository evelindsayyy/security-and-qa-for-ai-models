#!/usr/bin/env python3
"""
Map Garak JSONL report output to SafetyResult-shaped JSON (docs/data-model.md).

Prefers garak ``eval`` summary rows (passed/fails per probe). Falls back to
aggregating ``attempt`` rows when eval summaries are not present yet.

Usage:
    python export_safety_result.py output/garak-gpt41mini-low-guardrail.report.jsonl
    python export_safety_result.py output/garak-gpt41mini-low-guardrail.report.jsonl \\
        -o output/safety_result.json
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROBE_CATEGORY: dict[str, str] = {
    "misleading": "policy",
    "packagehallucination": "policy",
    "snowball": "policy",
}

DEFAULT_DEPLOYMENT_CONTEXT = {
    "deployment_type": "chatbot",
    "has_tools": False,
    "has_guardrails": True,
    "data_access": "none",
    "commercial_vs_oss": "commercial",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_input(path: Path) -> Path:
    if path.exists():
        return path
    matches = sorted(glob.glob(str(path)))
    if not matches:
        raise FileNotFoundError(f"No report file matched: {path}")
    return Path(matches[-1])


def _probe_module(name: str) -> str:
    return name.split(".")[0] if "." in name else name


def _load_rows(report_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with report_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _findings_from_eval_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one finding per garak eval summary (probe + detector)."""
    eval_rows = [r for r in rows if r.get("entry_type") == "eval"]
    if not eval_rows:
        return []

    # Roll up eval rows by probe module (e.g. packagehallucination.* → one module).
    by_module: dict[str, dict[str, int]] = defaultdict(lambda: {"passed": 0, "fails": 0, "total": 0})
    probe_labels: dict[str, str] = {}

    for row in eval_rows:
        probe = str(row.get("probe") or "unknown")
        module = _probe_module(probe)
        probe_labels[module] = probe
        by_module[module]["passed"] += int(row.get("passed") or 0)
        by_module[module]["fails"] += int(row.get("fails") or 0)
        by_module[module]["total"] += int(row.get("total_evaluated") or 0)

    findings: list[dict[str, Any]] = []
    for module, stats in sorted(by_module.items()):
        fails = stats["fails"]
        total = stats["total"]
        ok = fails == 0
        findings.append(
            {
                "id": str(uuid.uuid4()),
                "category": PROBE_CATEGORY.get(module, "policy"),
                "source": "garak",
                "passed": ok,
                "severity": "medium" if ok else "high",
                "title": f"garak probe module: {module}",
                "description": (
                    f"{stats['passed']}/{total} attempts passed detector "
                    f"({fails} attack hit(s)); example probe: {probe_labels[module]}"
                ),
                "probe_id": f"garak.{module}",
            }
        )
    return findings


def _attack_from_attempt(row: dict[str, Any], eval_threshold: float = 0.5) -> bool:
    detectors = row.get("detector_results") or {}
    for scores in detectors.values():
        if isinstance(scores, list) and scores:
            if float(scores[0]) >= eval_threshold:
                return True
    return row.get("status") == 1  # garak status 1 = fail in some versions


def _findings_from_attempt_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts = [r for r in rows if r.get("entry_type") == "attempt" and r.get("detector_results")]
    if not attempts:
        return []

    by_module: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        probe = str(row.get("probe_classname") or row.get("probe") or "unknown")
        by_module[_probe_module(probe)].append(row)

    findings: list[dict[str, Any]] = []
    for module, group in sorted(by_module.items()):
        hits = sum(1 for a in group if _attack_from_attempt(a))
        ok = hits == 0
        findings.append(
            {
                "id": str(uuid.uuid4()),
                "category": PROBE_CATEGORY.get(module, "policy"),
                "source": "garak",
                "passed": ok,
                "severity": "medium" if ok else "high",
                "title": f"garak probe module: {module}",
                "description": f"{len(group)} attempt(s), {hits} attack hit(s) (partial report)",
                "probe_id": f"garak.{module}",
            }
        )
    return findings


def export_from_garak_report(
    report_path: Path,
    *,
    probe_suite: str = "garak_subset_v1",
    gateway_model_id: str = "GPT 4.1 Mini",
) -> dict[str, Any]:
    rows = _load_rows(report_path)
    if not rows:
        raise ValueError(f"No JSONL rows in {report_path}")

    findings = _findings_from_eval_rows(rows)
    if not findings:
        findings = _findings_from_attempt_rows(rows)
    if not findings:
        raise ValueError(
            "No eval or scored attempt rows found — scan may still be running or failed early."
        )

    passed = sum(1 for f in findings if f["passed"])
    n = len(findings)
    pass_rate = (passed / n) if n else 0.0

    init_row = next((r for r in rows if r.get("entry_type") == "init"), {})
    target = gateway_model_id
    for row in rows:
        if row.get("plugins.target_name"):
            target = row["plugins.target_name"]
            break

    return {
        "gateway_model_id": str(target),
        "status": "complete",
        "deployment_context": DEFAULT_DEPLOYMENT_CONTEXT,
        "probe_suite": probe_suite,
        "summary_pass_rate": round(pass_rate, 4),
        "tool_results": {
            "garak": {
                "report_file": str(report_path),
                "garak_version": init_row.get("garak_version"),
                "run_id": init_row.get("run"),
            }
        },
        "started_at": init_row.get("start_time") or _utc_now(),
        "completed_at": _utc_now(),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Garak JSONL report to SafetyResult-shaped JSON."
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Garak .report.jsonl path (glob ok)",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output path")
    parser.add_argument("--probe-suite", default="garak_subset_v1")
    args = parser.parse_args()

    try:
        report_path = _resolve_input(args.input)
        doc = export_from_garak_report(report_path, probe_suite=args.probe_suite)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out = args.output or (report_path.parent / "safety_result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    n = len(doc["findings"])
    print(f"Wrote {out}")
    print(
        f"  gateway_model_id={doc['gateway_model_id']}  "
        f"pass_rate={doc['summary_pass_rate']:.0%}  findings={n}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
