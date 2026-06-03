"""build modelscan scanned vs skipped summary for gap map doc."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scanner.download import download_model
from scanner.format_detector import summarize as format_summarize
from scanner.paths import dump_json, model_dir, output_dir
from scanner.pickle_scan import find_pickle_weights, run_modelscan


def _skipped_details(summary: dict[str, Any]) -> dict[str, Any]:
    skipped = summary.get("skipped", {})
    scanned = summary.get("scanned", {})
    return {
        "total_skipped": skipped.get("total_skipped", 0),
        "skipped_files": skipped.get("skipped_files", skipped.get("files", []))[:50],
        "scanned_files": scanned.get("scanned_files", []),
        "scanned_count": len(scanned.get("scanned_files", [])),
    }


def collect_gap_for_model(model_id: str, *, auto_download: bool = True) -> dict[str, Any]:
    mdir = model_dir(model_id)
    if not mdir.exists() and auto_download:
        download_model(model_id)
    if not mdir.exists():
        raise FileNotFoundError(f"cannot gap-map without model dir: {mdir}")

    payload = run_modelscan(mdir)
    summary = payload.get("summary", {})
    fmt = format_summarize(mdir)
    pickle_path = find_pickle_weights(mdir)

    return {
        "model_id": model_id,
        "total_issues": summary.get("total_issues", 0),
        "total_issues_by_severity": summary.get("total_issues_by_severity", {}),
        "modelscan_version": summary.get("modelscan_version"),
        "scan_skipped": _skipped_details(summary),
        "format_flags": fmt.flags,
        "fickling_target": str(pickle_path) if pickle_path else None,
    }


def collect_gap_map(model_ids: list[str]) -> dict[str, Any]:
    entries = []
    for mid in model_ids:
        entries.append(collect_gap_for_model(mid))
    return {"models": entries}


def format_markdown_table(report: dict[str, Any]) -> str:
    lines = [
        "| model | scanned files | skipped (total) | issues | fickling target | safetensors_only |",
        "|-------|---------------|-----------------|--------|-----------------|------------------|",
    ]
    for row in report.get("models", []):
        sk = row.get("scan_skipped", {})
        flags = row.get("format_flags", {})
        lines.append(
            f"| {row['model_id']} | {sk.get('scanned_count', 0)} | "
            f"{sk.get('total_skipped', 0)} | {row.get('total_issues', 0)} | "
            f"{row.get('fickling_target') or 'n/a'} | {flags.get('safetensors_only', False)} |"
        )
    return "\n".join(lines)


def write_gap_map(model_ids: list[str]) -> dict[str, Any]:
    from scanner.paths import OUTPUT_ROOT

    report = collect_gap_map(model_ids)
    dump_json(OUTPUT_ROOT / "gap_map_summary.json", report)
    return report
