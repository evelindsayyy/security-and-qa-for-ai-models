"""
Week 3 spike: Trivy filesystem scan on a downloaded HF model directory.

- Not part of python -m scanner scan until week 4 product decision.
- Requires weights: python -m scanner scan <MODEL_ID> first.
- Writes: scanner/output/<slug>/trivy_report.json
- Image: scanner/docker/compose.trivy.yml
"""

import json
import os
import subprocess
from pathlib import Path

from scanner.paths import dump_json, model_dir, output_dir


def run_trivy(model_dir: Path) -> dict:
    """Filesystem CVE scan via Trivy CLI (exit 0 or 1 still yields JSON)."""
    result = subprocess.run(
        ["trivy", "fs", "--format", "json", "--quiet", str(model_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"trivy failed (exit {result.returncode}):\n{result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def main() -> None:
    """Scan MODEL_ID weights dir and write trivy_report.json next to other scan outputs."""
    model_id = os.environ.get("MODEL_ID", "distilbert-base-uncased")
    mdir = model_dir(model_id)
    out = output_dir(model_id)
    if not mdir.exists():
        raise FileNotFoundError(f"{mdir} missing — run: python -m scanner scan {model_id}")

    payload = run_trivy(mdir)
    dump_json(out / "trivy_report.json", payload)
    print(f"wrote {out}/trivy_report.json")


if __name__ == "__main__":
    main()
