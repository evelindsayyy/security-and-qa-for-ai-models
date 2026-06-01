"""run modelscan on /models/<MODEL_ID>/ — writes json + txt to /output/<MODEL_ID>/."""

from scan_helpers import (
    dump_json,
    format_modelscan_text,
    get_model_dir,
    get_model_id,
    output_dir,
    run_modelscan,
)


def main() -> None:
    model_id = get_model_id()
    model_dir = get_model_dir(model_id)
    out = output_dir(model_id)

    if not model_dir.exists():
        raise FileNotFoundError(f"{model_dir} not found — run download_model.py first")

    print(f"running modelscan on {model_dir} ...")
    payload = run_modelscan(model_dir)

    dump_json(out / "modelscan_report.json", payload)
    (out / "modelscan_report.txt").write_text(format_modelscan_text(payload))

    print(f"wrote {out}/modelscan_report.json")
    print(f"  total issues: {payload.get('summary', {}).get('total_issues', 0)}")


if __name__ == "__main__":
    main()
