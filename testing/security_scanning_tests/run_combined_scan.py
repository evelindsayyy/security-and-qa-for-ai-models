"""merge modelscan + fickling into one json — see docs/security-framework.md."""

from datetime import datetime, timezone

from scan_helpers import (
    analyze_pytorch_bin,
    dump_json,
    find_pickle_weights,
    get_model_dir,
    get_model_id,
    modelscan_summary_trimmed,
    modelscan_tier,
    output_dir,
    run_modelscan,
)


def main() -> None:
    model_id = get_model_id()
    model_dir = get_model_dir(model_id)
    out = output_dir(model_id)
    bin_file = find_pickle_weights(model_dir)

    if not model_dir.exists():
        raise FileNotFoundError(f"{model_dir} not found — run download_model.py first")

    print(f"running combined scan for {model_id} ...")
    modelscan = run_modelscan(model_dir)
    ms_summary = modelscan_summary_trimmed(modelscan)

    fickling = None
    if bin_file:
        fickling = analyze_pytorch_bin(bin_file)

    combined = {
        "model_id": model_id,
        "scanned_files": ms_summary.get("scanned_files", []),
        "overall_risk_score": 0,
        "severity_tier": modelscan_tier(modelscan),
        "fickling_severity": fickling["severity"] if fickling else None,
        "findings": modelscan.get("issues", []),
        "tool_results": {
            "modelscan": ms_summary,
            "fickling": fickling,
        },
        "scan_metadata": {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "scanner_version": "security_scanning_tests-0.1.0",
        },
    }

    dump_json(out / "combined_scan.json", combined)
    print(f"wrote {out}/combined_scan.json")
    print(f"  modelscan tier: {combined['severity_tier']}")
    print(f"  fickling severity: {combined['fickling_severity']}")


if __name__ == "__main__":
    main()
