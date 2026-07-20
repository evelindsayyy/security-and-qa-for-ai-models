"""
CLI entry point for the ``scanner`` package.

Production command (Docker or host with deps installed):

  python -m scanner scan gpt2

Debug / partial runs (same download layout under ``scanner/models``):

  python -m scanner metadata gpt2
  python -m scanner modelscan gpt2
  python -m scanner fickling gpt2
  python -m scanner modelaudit gpt2
  python -m scanner deps gpt2
  python -m scanner secrets gpt2
  python -m scanner refresh-supply-chain gpt2   # deps+secrets only, keep artifact results
  python -m scanner refresh-supply-chain --all

See ``scanner/README.md`` for calibration examples and output paths.
"""

from __future__ import annotations

import argparse
import json
import sys

from scanner.metadata import build_metadata_report
from scanner.paths import dump_json, model_dir, output_dir
from scanner.pickle_scan import (
    run_fickling_if_applicable,
    run_modelscan,
)
from scanner.format_detector import summarize as format_summarize
from scanner.modelaudit_scan import run_modelaudit_scoped
from scanner.dependency_scan import run_dependency_scan
from scanner.secret_scan import run_trufflehog
from scanner.pipeline import refresh_all_supply_chain, refresh_supply_chain, scan_model
from scanner.report_text import (
    format_fickling_text,
    format_modelaudit_text,
    format_modelscan_text,
)
from scanner.schemas import ScanResult, build_scan_result_from_combined


def _ensure_model(model_id: str) -> None:
    """Download weights when ``models/<slug>`` is incomplete or missing."""
    from scanner.download import download_model, model_download_complete

    if not model_download_complete(model_id):
        download_model(model_id)


def cmd_scan(args: argparse.Namespace) -> int:
    """Full pipeline: download → tools → ``scan_result.json``."""
    from scanner.download import DownloadError

    for model_id in args.models:
        print(f"scanning {model_id} ...", flush=True)
        try:
            result = scan_model(
                model_id,
                auto_download=True,
                run_modelscan=not args.skip_modelscan,
                run_fickling=not args.skip_fickling,
                run_modelaudit=not args.skip_modelaudit,
                run_dependencies=not args.skip_deps,
                run_secrets=not args.skip_secrets,
            )
        except DownloadError as exc:
            print(f"ERROR: {exc}", file=sys.stderr, flush=True)
            return 1
        except Exception as exc:
            from dbutils.run_lock import RunLockError

            if isinstance(exc, RunLockError):
                print(f"ERROR: {exc}", file=sys.stderr, flush=True)
                return 2
            print(f"ERROR: scan failed for {model_id}: {exc}", file=sys.stderr, flush=True)
            import traceback

            traceback.print_exc(file=sys.stderr)
            return 1
        out = output_dir(model_id) / "scan_result.json"
        print(
            f"  tier={result.severity_tier.value} score={result.overall_risk_score} "
            f"findings={len(result.findings)}"
        )
        print(f"  wrote {out}")
    return 0


def cmd_metadata(args: argparse.Namespace) -> int:
    """Hub inventory only — no ModelScan/Fickling (fast catalog check)."""
    for model_id in args.models:
        report = build_metadata_report(model_id)
        dump_json(output_dir(model_id) / "metadata.json", report)
        print(json.dumps({k: report[k] for k in ("model_id", "file_count", "scan_hints")}, indent=2))
    return 0


def cmd_modelscan(args: argparse.Namespace) -> int:
    """Debug: run ModelScan alone; write ``modelscan_report.json`` + ``.txt`` summary."""
    for model_id in args.models:
        _ensure_model(model_id)
        mdir = model_dir(model_id)
        out = output_dir(model_id)
        payload = run_modelscan(mdir)
        dump_json(out / "modelscan_report.json", payload)
        (out / "modelscan_report.txt").write_text(format_modelscan_text(payload))
        print(f"{model_id}: issues={payload.get('summary', {}).get('total_issues', 0)} -> {out}")
    return 0


def cmd_fickling(args: argparse.Namespace) -> int:
    """Debug: run Fickling on all pickle-family weights in the repo."""
    for model_id in args.models:
        _ensure_model(model_id)
        mdir = model_dir(model_id)
        out = output_dir(model_id)
        report = run_fickling_if_applicable(mdir)
        if not report:
            print(f"{model_id}: no pickle weights — fickling skipped")
            continue
        dump_json(out / "fickling_report.json", report)
        (out / "fickling_report.txt").write_text(format_fickling_text(report))
        print(f"{model_id}: severity={report['severity']} -> {out}")
    return 0


def cmd_modelaudit(args: argparse.Namespace) -> int:
    """
    Debug: ModelAudit with same scoping as full scan (content-routed, noise filtered).

    Re-runs ModelScan + Fickling only to supply context for actionable filtering.
    """
    for model_id in args.models:
        _ensure_model(model_id)
        mdir = model_dir(model_id)
        out = output_dir(model_id)
        fmt = format_summarize(mdir)
        ms = run_modelscan(mdir)
        fick = run_fickling_if_applicable(mdir)
        report = run_modelaudit_scoped(mdir, fmt, ms, fickling_report=fick)
        if not report:
            print(f"{model_id}: modelaudit unavailable or no report")
            continue
        dump_json(out / "modelaudit_report.json", report)
        (out / "modelaudit_report.txt").write_text(format_modelaudit_text(report))
        print(format_modelaudit_text(report))
        print(f"-> {out}/modelaudit_report.json")
    return 0


def cmd_deps(args: argparse.Namespace) -> int:
    """Debug: pip-audit + OSV dependency scan only."""
    for model_id in args.models:
        _ensure_model(model_id)
        mdir = model_dir(model_id)
        out = output_dir(model_id)
        report = run_dependency_scan(mdir)
        if not report:
            print(f"{model_id}: no dependency manifests found")
            continue
        dump_json(out / "dependency_report.json", report)
        print(
            f"{model_id}: vulns={report.get('vuln_count', 0)} "
            f"manifests={report.get('manifests_found')} -> {out}/dependency_report.json"
        )
    return 0


def cmd_secrets(args: argparse.Namespace) -> int:
    """Debug: TruffleHog secret scan only."""
    for model_id in args.models:
        _ensure_model(model_id)
        mdir = model_dir(model_id)
        out = output_dir(model_id)
        report = run_trufflehog(mdir)
        if not report:
            print(f"{model_id}: secret scan unavailable")
            continue
        dump_json(out / "trufflehog_report.json", report)
        print(
            f"{model_id}: secrets={report.get('secret_count', 0)} "
            f"verified={report.get('verified_count', 0)} "
            f"available={report.get('available')} -> {out}/trufflehog_report.json"
        )
    return 0


def cmd_refresh_supply_chain(args: argparse.Namespace) -> int:
    """Run deps + secrets only; merge into existing scan_result.json and rescore."""
    if args.all:
        rows = refresh_all_supply_chain()
        for model_id, outcome in rows:
            if isinstance(outcome, ScanResult):
                deps = (outcome.tool_results or {}).get("dependencies") or {}
                sec = (outcome.tool_results or {}).get("secrets") or {}
                print(
                    f"{model_id}: tier={outcome.severity_tier.value} "
                    f"deps={deps.get('vuln_count', 0) if deps else 0} "
                    f"secrets={sec.get('secret_count', 0) if sec else 0}"
                )
            else:
                print(f"{model_id}: FAILED — {outcome}", file=sys.stderr)
        return 0

    for model_id in args.models:
        print(f"refreshing supply-chain for {model_id} ...")
        result = refresh_supply_chain(model_id)
        deps = (result.tool_results or {}).get("dependencies") or {}
        sec = (result.tool_results or {}).get("secrets") or {}
        print(
            f"  tier={result.severity_tier.value} score={result.overall_risk_score} "
            f"deps={deps.get('vuln_count', 0) if deps else 0} "
            f"secrets={sec.get('secret_count', 0) if sec else 0} "
            f"trufflehog={'yes' if sec.get('available') else 'skipped'}"
        )
        print(f"  wrote {output_dir(model_id) / 'scan_result.json'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Pydantic-validate existing JSON on disk.

    Accepts ``scan_result.json`` or legacy ``combined_scan.json``.
    """
    for model_id in args.models:
        path = output_dir(model_id) / (args.file or "scan_result.json")
        if not path.is_file():
            path = output_dir(model_id) / "combined_scan.json"
        if not path.is_file():
            print(f"missing output for {model_id} — run: python -m scanner scan {model_id}", file=sys.stderr)
            return 1
        data = json.loads(path.read_text())
        if "status" in data and "severity_tier" in data:
            validated = ScanResult.model_validate(data)
        else:
            validated = build_scan_result_from_combined(data)
        print(f"{model_id}: tier={validated.severity_tier} findings={len(validated.findings)}")
    return 0


def main() -> int:
    """Parse argv and dispatch to subcommand handlers."""
    parser = argparse.ArgumentParser(
        prog="scanner",
        description="Track A HF artifact scanner (package: scanner/)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    refresh_parser = sub.add_parser(
        "refresh-supply-chain",
        help="deps+secrets only; update existing scan_result.json",
    )
    refresh_parser.add_argument(
        "models",
        nargs="*",
        help="HF repo ids (omit when using --all)",
    )
    refresh_parser.add_argument(
        "--all",
        action="store_true",
        help="refresh every scan_result.json under output/",
    )
    refresh_parser.set_defaults(func=cmd_refresh_supply_chain)

    scan_parser = sub.add_parser("scan", help="full pipeline -> scan_result.json")
    scan_parser.add_argument("models", nargs="+")
    for flag, dest in [
        ("--skip-modelscan", "skip_modelscan"),
        ("--skip-fickling", "skip_fickling"),
        ("--skip-modelaudit", "skip_modelaudit"),
        ("--skip-deps", "skip_deps"),
        ("--skip-secrets", "skip_secrets"),
    ]:
        scan_parser.add_argument(flag, action="store_true")
    scan_parser.set_defaults(func=cmd_scan)

    for name, func, help_text in [
        ("metadata", cmd_metadata, "hf hub file list only"),
        ("modelscan", cmd_modelscan, "modelscan only (debug)"),
        ("fickling", cmd_fickling, "fickling only (debug)"),
        ("modelaudit", cmd_modelaudit, "modelaudit only (debug; content-routed)"),
        ("deps", cmd_deps, "pip-audit + OSV only (debug)"),
        ("secrets", cmd_secrets, "trufflehog only (debug)"),
        ("validate", cmd_validate, "pydantic-check existing json"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("models", nargs="+")
        if name == "validate":
            p.add_argument("--file", default=None, help="default scan_result.json")
        p.set_defaults(func=func)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
