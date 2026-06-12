"""
End-to-end HF artifact scan orchestration.

This module wires the production pipeline (see ``scanner/README.md``):

  download (optional) → format_detector → ModelScan → Fickling → ModelAudit
  → dependency scan (pip-audit + OSV) → secret scan (TruffleHog)
  → risk_scorer → write scan_result.json (+ debug reports)

Individual tools are also exposed via CLI debug commands in ``__main__.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner import __version__
from scanner.download import download_model
from scanner.format_detector import FileFormatSummary, summarize as format_summarize
from scanner.format_detector import summary_to_metadata_dict
from scanner.modelaudit_scan import run_modelaudit_scoped
from scanner.dependency_scan import run_dependency_scan
from scanner.secret_scan import run_trufflehog
from scanner.paths import (
    delete_model_weights,
    dump_json,
    list_scan_output_slugs,
    model_dir,
    output_dir,
    slug_to_model_id,
    weights_retained,
)
from scanner.pickle_scan import (
    modelscan_summary_trimmed,
    run_fickling_if_applicable,
    run_modelscan as execute_modelscan,
)
from scanner.risk_scorer import score as risk_score
from scanner.schemas import ScanResult, build_scan_result, build_scan_result_from_combined


def _modelscan_payload_from_tool(ms: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a minimal ModelScan payload from trimmed ``tool_results`` for rescoring."""
    return {
        "summary": {
            "total_issues": ms.get("total_issues", 0),
            "total_issues_by_severity": ms.get("total_issues_by_severity") or {},
            "skipped": {"total_skipped": ms.get("total_skipped", 0)},
        },
        "issues": ms.get("issues") or [],
    }


def _format_summary_from_metadata(meta: dict[str, Any]) -> FileFormatSummary | None:
    if not meta:
        return None
    try:
        return FileFormatSummary.model_validate(meta)
    except Exception:
        return None


def _load_existing_scan(hf_repo: str) -> ScanResult:
    path = output_dir(hf_repo) / "scan_result.json"
    if not path.is_file():
        raise FileNotFoundError(f"no scan_result.json for {hf_repo} — run scan first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "status" in data and "severity_tier" in data:
        return ScanResult.model_validate(data)
    return build_scan_result_from_combined(data)


def refresh_supply_chain(hf_repo: str) -> ScanResult:
    """
    Run pip-audit/OSV + TruffleHog only; merge into an existing ``scan_result.json``.

    Re-scores using stored artifact tool results (ModelScan/Fickling/ModelAudit) so
    heavy scanners are not re-run. Use after upgrading scanner deps/secrets support.
    """
    existing = _load_existing_scan(hf_repo)
    mdir = model_dir(hf_repo)
    if not mdir.is_dir():
        raise FileNotFoundError(f"{mdir} missing — cannot refresh supply-chain scan")

    dependencies = run_dependency_scan(mdir)
    secrets = run_trufflehog(mdir)
    if dependencies is None:
        dependencies = {
            "manifests_found": [],
            "vuln_count": 0,
            "vulnerabilities": [],
            "by_severity": {},
            "scan_mode": "pip_audit_plus_osv",
        }

    tool = dict(existing.tool_results or {})
    tool["dependencies"] = dependencies
    tool["secrets"] = secrets

    ms = tool.get("modelscan") or {}
    fickling = tool.get("fickling")
    modelaudit = tool.get("modelaudit")
    format_summary = _format_summary_from_metadata(
        (existing.scan_metadata or {}).get("file_formats") or {}
    )

    risk = risk_score(
        hf_repo,
        _modelscan_payload_from_tool(ms),
        fickling,
        format_summary,
        modelaudit_summary=modelaudit,
        dependency_summary=dependencies,
        secret_summary=secrets,
    )

    scan_metadata = dict(existing.scan_metadata or {})
    coverage = dict(scan_metadata.get("coverage") or {})
    coverage["dependency_manifests"] = (dependencies or {}).get("manifests_found") or []
    coverage["secret_scan_available"] = (secrets or {}).get("available", False)
    coverage["secret_files_scanned"] = (secrets or {}).get("files_scanned")
    scan_metadata["coverage"] = coverage
    scan_metadata["scanner_version"] = __version__
    scan_metadata["supply_chain_refreshed_at"] = datetime.now(timezone.utc).isoformat()

    result = build_scan_result(
        existing.model_id,
        risk,
        list(existing.scanned_files or []),
        tool,
        scan_metadata,
        fickling_severity=existing.fickling_severity
        or (fickling.get("severity") if isinstance(fickling, dict) else None),
    )

    out = output_dir(hf_repo)
    dump_json(out / "scan_result.json", result.model_dump(mode="json"))
    if dependencies and dependencies.get("vuln_count"):
        dump_json(out / "dependency_report.json", dependencies)
    dump_json(out / "trufflehog_report.json", secrets or {"available": False})
    return result


def refresh_all_supply_chain() -> list[tuple[str, ScanResult | str]]:
    """Refresh every model under ``output/`` that has ``scan_result.json``."""
    results: list[tuple[str, ScanResult | str]] = []
    for slug in list_scan_output_slugs():
        hf_repo = slug_to_model_id(slug)
        path = output_dir(hf_repo) / "scan_result.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            hf_repo = data.get("model_id") or hf_repo
        except Exception:
            pass
        try:
            results.append((hf_repo, refresh_supply_chain(hf_repo)))
        except Exception as exc:
            results.append((hf_repo, str(exc)))
    return results


def scan_model(
    hf_repo: str,
    *,
    auto_download: bool = True,
    write_combined: bool = True,
    run_modelscan: bool = True,
    run_fickling: bool = True,
    run_modelaudit: bool = True,
    run_dependencies: bool = True,
    run_secrets: bool = True,
) -> ScanResult:
    """
    Run the full Track A scan for one Hugging Face repo id.

    Args:
        hf_repo: Hub id (e.g. ``gpt2``, ``BAAI/bge-small-en-v1.5``).
        auto_download: If weights are missing, call ``download_model``.
        write_combined: Also emit legacy ``combined_scan.json`` for fixtures/tests.

    Returns:
        Validated ``ScanResult`` (also written to ``output/<slug>/scan_result.json``).

    Side effects:
        Writes ``modelscan_report.json``, ``modelaudit_report.json`` when applicable,
        and populates ``tool_results`` / ``scan_metadata.coverage`` for reviewers.
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

    # Step 1: inventory file types (safetensors-only skips Fickling in risk scorer).
    format_summary = format_summarize(mdir)

    # Step 2–4: defense-in-depth scanners (overlap is intentional; deduped later).
    modelscan_payload = (
        execute_modelscan(mdir)
        if run_modelscan
        else {"summary": {"total_issues": 0}, "scanned_files": []}
    )
    fickling = run_fickling_if_applicable(mdir) if run_fickling else None
    modelaudit = (
        run_modelaudit_scoped(mdir, format_summary, modelscan_payload, fickling_report=fickling)
        if run_modelaudit
        else None
    )

    # Step 5–6: supply-chain and secret scanning (graceful skip when no manifests/binary).
    dependencies = run_dependency_scan(mdir) if run_dependencies else None
    secrets = run_trufflehog(mdir) if run_secrets else None
    if dependencies is None:
        dependencies = {
            "manifests_found": [],
            "vuln_count": 0,
            "vulnerabilities": [],
            "by_severity": {},
            "scan_mode": "pip_audit_plus_osv",
        }

    # Step 7: merge tool outputs into tier, score, and normalized findings[].
    risk = risk_score(
        hf_repo,
        modelscan_payload,
        fickling,
        format_summary,
        modelaudit_summary=modelaudit,
        dependency_summary=dependencies,
        secret_summary=secrets,
    )
    ms_trimmed = modelscan_summary_trimmed(modelscan_payload)

    tool_results: dict[str, Any] = {
        "modelscan": ms_trimmed,
        "fickling": fickling,
        "modelaudit": modelaudit,
        "dependencies": dependencies,
        "secrets": secrets,
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
            "dependency_manifests": (dependencies or {}).get("manifests_found") or [],
            "secret_scan_available": (secrets or {}).get("available", False),
            "secret_files_scanned": (secrets or {}).get("files_scanned"),
        },
    }

    # Union of paths touched by ModelScan and ModelAudit for the scans.scanned_files field.
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

    if not weights_retained():
        delete_model_weights(hf_repo)

    if write_combined:
        # Legacy flat JSON kept for unit test fixtures and spike comparisons.
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

    # Raw tool dumps for debugging without re-running heavy scans.
    dump_json(out / "modelscan_report.json", modelscan_payload)
    if modelaudit and (modelaudit.get("paths_scanned") or modelaudit.get("issues")):
        dump_json(out / "modelaudit_report.json", modelaudit)
    if dependencies and dependencies.get("vuln_count"):
        dump_json(out / "dependency_report.json", dependencies)
    if secrets and (secrets.get("secret_count") or secrets.get("available") is False):
        dump_json(out / "trufflehog_report.json", secrets)
    return result


def scan_model_to_path(hf_repo: str, output_path: Path | None = None) -> Path:
    """
    Convenience wrapper: run ``scan_model`` and optionally override output path.

    Used by tests and future Celery tasks that need a explicit filesystem target.
    """
    result = scan_model(hf_repo)
    path = output_path or (output_dir(hf_repo) / "scan_result.json")
    dump_json(path, result.model_dump(mode="json"))
    return path
