"""
Week 2 spike: compare OSV API vs pip-audit on a known-vulnerable pin.

- Not imported by scanner.pipeline or python -m scanner scan.
- Run manually in Docker: see scanner/experiments/README.md
- Writes: scanner/output/osv_pip_audit_spike/

Test pin: pillow==8.1.0
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from scanner.paths import OUTPUT_ROOT

PACKAGE_NAME = "pillow"
PACKAGE_VERSION = "8.1.0"
REQUIREMENT_LINE = f"{PACKAGE_NAME}=={PACKAGE_VERSION}"
OSV_QUERY_URL = "https://api.osv.dev/v1/query"


def query_osv(name: str, version: str) -> dict:
    """POST a single PyPI package version to the OSV query API."""
    payload = {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
    resp = requests.post(OSV_QUERY_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_osv_summary(osv_response: dict) -> list[dict]:
    """Flatten OSV vuln list to id + short summary for console comparison."""
    rows = []
    for vuln in osv_response.get("vulns", []):
        rows.append({"id": vuln.get("id", "?"), "summary": vuln.get("summary", "")[:80]})
    return rows


def run_pip_audit(requirement_line: str) -> tuple[list[dict], str]:
    """Run pip-audit in a temp requirements file; return (vuln rows, stderr)."""
    with tempfile.TemporaryDirectory() as tmp:
        req_path = Path(tmp) / "requirements.txt"
        req_path.write_text(requirement_line + "\n")
        cache_dir = OUTPUT_ROOT / ".cache" / "pip-audit"
        cache_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["XDG_CACHE_HOME"] = str((OUTPUT_ROOT / ".cache").resolve())
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "-r", str(req_path), "--format", "json", "--progress-spinner", "off"],
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode not in (0, 1):
            raise RuntimeError(f"pip-audit failed:\n{proc.stderr}")
        if not proc.stdout.strip():
            return [], proc.stderr
        data = json.loads(proc.stdout)
        if isinstance(data, dict) and "dependencies" in data:
            rows = []
            for dep in data["dependencies"]:
                for vuln in dep.get("vulns", []):
                    rows.append({**vuln, "name": dep.get("name"), "version": dep.get("version")})
            return rows, proc.stderr
        return data if isinstance(data, list) else [], proc.stderr


def extract_pip_audit_ids(audit_rows: list[dict]) -> set[str]:
    """Collect CVE/GHSA/PYSEC ids from pip-audit JSON for overlap stats."""
    ids: set[str] = set()
    for row in audit_rows:
        if row.get("id"):
            ids.add(row["id"])
        for alias in row.get("aliases", []):
            if alias.startswith(("CVE-", "GHSA-", "PYSEC-")):
                ids.add(alias)
    return ids


def main() -> None:
    """Compare OSV vs pip-audit on pillow==8.1.0 and write spike JSON under output/."""
    osv_raw = query_osv(PACKAGE_NAME, PACKAGE_VERSION)
    osv_rows = extract_osv_summary(osv_raw)
    pip_rows, _ = run_pip_audit(REQUIREMENT_LINE)
    osv_ids = {r["id"] for r in osv_rows}
    pip_ids = extract_pip_audit_ids(pip_rows)
    print(f"osv ids: {len(osv_ids)}, pip-audit ids: {len(pip_ids)}, overlap: {len(osv_ids & pip_ids)}")
    out_dir = OUTPUT_ROOT / "osv_pip_audit_spike"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "osv_response.json").write_text(json.dumps(osv_raw, indent=2))
    (out_dir / "pip_audit_response.json").write_text(json.dumps(pip_rows, indent=2))
    print(f"saved under {out_dir}/")


if __name__ == "__main__":
    main()
