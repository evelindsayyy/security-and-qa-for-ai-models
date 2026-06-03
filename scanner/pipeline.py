"""End-to-end HF artifact scan → ScanResult JSON (Postgres-ready shapes)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner import __version__
from scanner.download import download_model
from scanner.format_detector import summarize as format_summarize
from scanner.format_detector import summary_to_metadata_dict
from scanner.modelaudit_scan import run_modelaudit_scoped
from scanner.paths import dump_json, model_dir, output_dir
from scanner.pickle_scan import (
    modelscan_summary_trimmed,
    run_fickling_if_applicable,
    run_modelscan,
)
from scanner.risk_scorer import score as risk_score
from scanner.schemas import ScanResult, build_scan_result


def scan_model(
    hf_repo: str,
    *,
    auto_download: bool = True,
    write_combined: bool = True,
) -> ScanResult:
    """
    Download (if needed), run ModelScan + Fickling + ModelAudit, score, write JSON.

    Output matches docs/data-model.md: scans row + findings[] for week 5 Postgres.
    """
    mdir = model_dir(hf_repo)
    if not mdir.exists() and auto_download:
        download_model(hf_repo)
    if not mdir.exists():
        raise FileNotFoundError(
            f"{mdir} not found — run download first or pass auto_download=True"
        )

    out = output_dir(hf_repo)
    out.mkdir(parents=True, exist_ok=True)

    format_summary = format_summarize(mdir)
    modelscan_payload = run_modelscan(mdir)
    fickling = run_fickling_if_applicable(mdir)
    modelaudit = run_modelaudit_scoped(mdir, format_summary, modelscan_payload)

    risk = risk_score(
        hf_repo,
        modelscan_payload,
        fickling,
        format_summary,
        modelaudit_summary=modelaudit,
    )
    ms_trimmed = modelscan_summary_trimmed(modelscan_payload)

    tool_results: dict[str, Any] = {
        "modelscan": ms_trimmed,
        "fickling": fickling,
        "modelaudit": modelaudit,
    }

    scan_metadata = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "scanner_version": __version__,
        "file_formats": summary_to_metadata_dict(format_summary),
        "coverage": {
            "modelscan_scanned_files": len(ms_trimmed.get("scanned_files") or []),
            "modelscan_skipped": ms_trimmed.get("total_skipped", 0),
            "modelaudit_paths": (modelaudit or {}).get("paths_scanned", []),
            "fickling_applicable": format_summary.flags.get("fickling_applicable", False),
        },
    }

    scanned_files = list(ms_trimmed.get("scanned_files") or [])
    for p in (modelaudit or {}).get("paths_scanned") or []:
        if p not in scanned_files:
            scanned_files.append(p)

    result = build_scan_result(
        hf_repo,
        risk,
        scanned_files,
        tool_results,
        scan_metadata,
        fickling_severity=fickling.get("severity") if fickling else None,
    )

    dump_json(out / "scan_result.json", result.model_dump(mode="json"))

    if write_combined:
        dump_json(
            out / "combined_scan.json",
            {
                "model_id": hf_repo,
                "scanned_files": scanned_files,
                "overall_risk_score": risk.overall_risk_score,
                "severity_tier": risk.severity_tier.value,
                "fickling_severity": fickling.get("severity") if fickling else None,
                "findings": [f.model_dump(mode="json") for f in risk.findings],
                "tool_results": tool_results,
                "scan_metadata": scan_metadata,
            },
        )

    dump_json(out / "modelscan_report.json", modelscan_payload)
    if modelaudit and (modelaudit.get("paths_scanned") or modelaudit.get("issues")):
        dump_json(out / "modelaudit_report.json", modelaudit)
    return result


def scan_model_to_path(hf_repo: str, output_path: Path | None = None) -> Path:
    result = scan_model(hf_repo)
    path = output_path or (output_dir(hf_repo) / "scan_result.json")
    dump_json(path, result.model_dump(mode="json"))
    return path
