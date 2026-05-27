"""run fickling on pickle weights in /models/<MODEL_ID>/ — writes json + txt to /output/<MODEL_ID>/."""

from scan_helpers import (
    analyze_pytorch_bin,
    dump_json,
    find_pickle_weights,
    format_fickling_text,
    get_model_dir,
    get_model_id,
    output_dir,
)


def main() -> None:
    model_id = get_model_id()
    model_dir = get_model_dir(model_id)
    out = output_dir(model_id)
    bin_file = find_pickle_weights(model_dir)

    if bin_file is None:
        raise FileNotFoundError(
            f"no pickle weights in {model_dir} — fickling needs pytorch_model.bin (or similar). "
            "safetensors-only repos skip fickling; modelscan still works."
        )

    print(f"running fickling on {bin_file} ...")
    report = analyze_pytorch_bin(bin_file)

    dump_json(out / "fickling_report.json", report)
    (out / "fickling_report.txt").write_text(format_fickling_text(report))

    print(f"wrote {out}/fickling_report.json")
    print(f"  severity: {report['severity']}, safe: {report['is_likely_safe']}")


if __name__ == "__main__":
    main()
