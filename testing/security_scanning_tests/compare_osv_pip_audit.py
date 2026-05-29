"""
compare OSV API vs pip-audit for the same vulnerable package.

why this script exists:
  - week 2 track A (security) needs to know where dependency scanners agree/disagree
  - model repos ship requirements.txt — we may query OSV without installing
  - pip-audit resolves/install context and wraps OSV + PyPI advisory data

test package: pillow==8.1.0
  - well-known CVEs in OSV (e.g. CVE-2021-27921 and related pillow 8.x issues)
  - stable pin so results are reproducible in the container
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

# --- config: one pinned vulnerable package ---
PACKAGE_NAME = "pillow"
PACKAGE_VERSION = "8.1.0"
REQUIREMENT_LINE = f"{PACKAGE_NAME}=={PACKAGE_VERSION}"

OSV_QUERY_URL = "https://api.osv.dev/v1/query"


def query_osv(name: str, version: str) -> dict:
    # direct OSV lookup — no pip install, just ecosystem + version
    payload = {
        "package": {"name": name, "ecosystem": "PyPI"},
        "version": version,
    }
    resp = requests.post(OSV_QUERY_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_osv_ids(osv_response: dict) -> set[str]:
    # OSV returns full vuln objects; we mostly care about ids for comparison
    return {v.get("id", "") for v in osv_response.get("vulns", []) if v.get("id")}


def extract_osv_summary(osv_response: dict) -> list[dict]:
    rows = []
    for vuln in osv_response.get("vulns", []):
        vid = vuln.get("id", "?")
        # severity is nested in database_specific or severity[] — keep it simple
        summary = vuln.get("summary", "")[:80]
        rows.append({"id": vid, "summary": summary})
    return rows


def run_pip_audit(requirement_line: str) -> tuple[list[dict], str]:
    # pip-audit needs a requirements file on disk
    with tempfile.TemporaryDirectory() as tmp:
        req_path = Path(tmp) / "requirements.txt"
        req_path.write_text(requirement_line + "\n")

        # non-root container can't write to /.cache — same issue we fixed for HF_HOME
        cache_dir = Path("/output") / ".cache" / "pip-audit"
        cache_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["XDG_CACHE_HOME"] = str(cache_dir.parent)

        # --format json for parsing; --desc on for human context in raw output
        cmd = [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(req_path),
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if proc.returncode not in (0, 1):
            # 1 = vulns found (expected for our test pin)
            raise RuntimeError(
                f"pip-audit failed (exit {proc.returncode}):\n{proc.stderr}"
            )

        if not proc.stdout.strip():
            return [], proc.stderr

        data = json.loads(proc.stdout)
        # pip-audit 2.x json: {"dependencies": [{"name", "version", "vulns": [...]}]}
        if isinstance(data, dict) and "dependencies" in data:
            rows = []
            for dep in data["dependencies"]:
                for vuln in dep.get("vulns", []):
                    rows.append({**vuln, "name": dep.get("name"), "version": dep.get("version")})
            return rows, proc.stderr
        return data if isinstance(data, list) else [], proc.stderr


def extract_pip_audit_ids(audit_rows: list[dict]) -> set[str]:
    ids: set[str] = set()
    for row in audit_rows:
        if row.get("id"):
            ids.add(row["id"])
        for alias in row.get("aliases", []):
            if alias.startswith("CVE-") or alias.startswith("GHSA-") or alias.startswith("PYSEC-"):
                ids.add(alias)
    return ids


def print_comparison(osv_rows: list[dict], pip_rows: list[dict]) -> None:
    osv_ids = {r["id"] for r in osv_rows}
    pip_ids = extract_pip_audit_ids(pip_rows)

    print("=" * 60)
    print(f"package: {PACKAGE_NAME}=={PACKAGE_VERSION}")
    print("=" * 60)

    print("\n--- OSV API (direct POST) ---")
    if not osv_rows:
        print("  (no vulns returned)")
    for row in osv_rows:
        print(f"  {row['id']}")
        if row.get("summary"):
            print(f"    {row['summary']}")

    print("\n--- pip-audit (requirements pin) ---")
    if not pip_rows:
        print("  (no vulns returned)")
    for row in pip_rows:
        name = row.get("name", "?")
        version = row.get("version", "?")
        vuln_id = row.get("id", "?")
        aliases = ", ".join(row.get("aliases", [])[:4])
        print(f"  {name} {version} -> {vuln_id}")
        if aliases:
            print(f"    aliases: {aliases}")

    # osv uses PYSEC/GHSA ids; pip-audit rows link via aliases — compare GHSA overlap too
    osv_ghsa = {i for i in osv_ids if i.startswith("GHSA-")}
    pip_ghsa = {i for i in pip_ids if i.startswith("GHSA-")}
    only_osv = osv_ids - pip_ids
    only_pip = pip_ids - osv_ids
    both = osv_ids & pip_ids
    ghsa_overlap = osv_ghsa & pip_ghsa

    print("\n--- overlap ---")
    print(f"  exact id match: {len(both)}")
    print(f"  GHSA overlap (osv vs pip aliases): {len(ghsa_overlap)}")
    print(f"  OSV only:    {len(only_osv)}")
    print(f"  pip-audit only: {len(only_pip)}")
    print(f"  pip-audit vuln rows: {len(pip_rows)}")
    if only_osv:
        print(f"    OSV only ids: {sorted(only_osv)[:10]}")
    if only_pip:
        print(f"    pip-audit only ids: {sorted(only_pip)[:10]}")

    print("\n--- what we learned (for the scanner design) ---")
    print("  - pip-audit wraps OSV/PyPI data and may add install-resolution context")
    print("  - OSV direct query works with just name+version (good for HF requirements.txt)")
    print("  - id sets won't match 1:1 (OSV-IDs vs GHSA/CVE aliases)")
    print("  - neither tool replaces modelscan/fickling on pickle weights")
    print("  - week 4: cross-ref severity with NVD; for now this spike is id comparison")


def main() -> None:
    print(f"querying OSV for {REQUIREMENT_LINE} ...")
    osv_raw = query_osv(PACKAGE_NAME, PACKAGE_VERSION)
    osv_rows = extract_osv_summary(osv_raw)

    print(f"running pip-audit for {REQUIREMENT_LINE} ...")
    pip_rows, pip_stderr = run_pip_audit(REQUIREMENT_LINE)
    if pip_stderr and "ERROR" in pip_stderr.upper():
        print(f"pip-audit stderr: {pip_stderr[:500]}", file=sys.stderr)

    print_comparison(osv_rows, pip_rows)

    # dump raw json for later reference in output dir if mounted
    out_dir = Path("/output") / "osv_pip_audit_spike"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "osv_response.json").write_text(json.dumps(osv_raw, indent=2))
    (out_dir / "pip_audit_response.json").write_text(json.dumps(pip_rows, indent=2))
    print(f"\nraw json saved to {out_dir}/")


if __name__ == "__main__":
    main()
