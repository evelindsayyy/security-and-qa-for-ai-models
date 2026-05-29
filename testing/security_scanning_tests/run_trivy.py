"""run trivy filesystem scan on /models/<MODEL_ID>/ — writes json + txt to /output/<MODEL_ID>/."""

import json
import subprocess
from pathlib import Path

from scan_helpers import dump_json, get_model_dir, get_model_id, output_dir


def run_trivy(model_dir: Path) -> dict:
    result = subprocess.run(
        ["trivy", "fs", "--format", "json", "--quiet", str(model_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"trivy failed (exit {result.returncode}):\n{result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


def format_trivy_text(payload: dict) -> str:
    results = payload.get("Results", [])
    if not results:
        return "no vulnerabilities found"
    lines = []
    for r in results:
        target = r.get("Target", "?")
        vulns = r.get("Vulnerabilities") or []
        lines.append(f"{target}: {len(vulns)} vulnerabilities")
        for v in vulns[:10]:
            vid = v.get("VulnerabilityID", "?")
            severity = v.get("Severity", "?")
            title = v.get("Title", "")[:60]
            lines.append(f"  [{severity}] {vid} {title}")
        if len(vulns) > 10:
            lines.append(f"  ... and {len(vulns) - 10} more (see trivy_report.json)")
    return "\n".join(lines)


def main() -> None:
    model_id = get_model_id()
    model_dir = get_model_dir(model_id)
    out = output_dir(model_id)

    if not model_dir.exists():
        raise FileNotFoundError(f"{model_dir} not found — run download_model.py first")

    print(f"running trivy on {model_dir} ...")
    payload = run_trivy(model_dir)

    dump_json(out / "trivy_report.json", payload)
    (out / "trivy_report.txt").write_text(format_trivy_text(payload))

    print(f"wrote {out}/trivy_report.json")
    total = sum(len(r.get("Vulnerabilities") or []) for r in payload.get("Results", []))
    print(f"  total vulnerabilities: {total}")


if __name__ == "__main__":
    main()
