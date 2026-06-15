"""
Dependency vulnerability scanning — pip-audit (Python tree) + OSV API (breadth/corroboration).

pip-audit resolves Python requirement files and queries vulnerability databases.
OSV corroborates pip-audit hits and covers non-Python manifests (package.json, go.mod, etc.).

Findings merge in ``risk_scorer`` with ``source`` pip_audit or osv and optional ``corroborated_by``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

from scanner.paths import OUTPUT_ROOT

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
OSV_QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"

_REQUIREMENTS_GLOB = ("requirements.txt", "requirements-dev.txt")
_REQUIREMENTS_PREFIX = "requirements"
_PYTHON_MANIFESTS = frozenset({"requirements", "pyproject", "setup"})
_NON_PYTHON_MANIFESTS = frozenset({"package.json", "go.mod", "Cargo.lock", "Gemfile.lock"})

_TIER_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

_PIN_RE = re.compile(
    r"^\s*([a-zA-Z0-9][a-zA-Z0-9._\-]*)\s*(?:==|>=|<=|~=|!=)\s*([^\s;#]+)",
    re.MULTILINE,
)


def find_requirement_files(model_dir: Path) -> list[dict[str, str]]:
    """
    Discover dependency manifest files under ``model_dir`` (skip ``.cache``).

    Returns list of ``{"path": rel_path, "kind": requirements|pyproject|...}``.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    for path in sorted(model_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(model_dir))
        if rel.startswith(".cache"):
            continue
        name = path.name.lower()
        if name in seen:
            continue

        kind: str | None = None
        if name in _REQUIREMENTS_GLOB or (
            name.startswith(_REQUIREMENTS_PREFIX) and name.endswith(".txt")
        ):
            kind = "requirements"
        elif name == "pyproject.toml":
            kind = "pyproject"
        elif name == "setup.py":
            kind = "setup"
        elif name in _NON_PYTHON_MANIFESTS:
            kind = name.replace(".", "_").replace("-", "_")

        if kind:
            seen.add(name)
            found.append({"path": rel, "kind": kind})

    return found


def _parse_requirements_pins(req_path: Path) -> list[tuple[str, str, str]]:
    """Extract ``(name, version, ecosystem)`` pins from a requirements file."""
    if not req_path.is_file():
        return []
    text = req_path.read_text(encoding="utf-8", errors="replace")
    pins: list[tuple[str, str, str]] = []
    for m in _PIN_RE.finditer(text):
        name, version = m.group(1), m.group(2).strip()
        if name and version and not version.startswith("git+"):
            pins.append((name.lower(), version, "PyPI"))
    return pins


def _pip_audit_available() -> bool:
    try:
        import pip_audit  # noqa: F401

        return True
    except ImportError:
        return False


def run_pip_audit(req_file: Path) -> tuple[list[dict[str, Any]], str]:
    """
    Run pip-audit on one requirements file; return ``(vuln_rows, stderr)``.

    Each row includes ``name``, ``version``, vuln fields, and ``manifest`` path.
    """
    if not _pip_audit_available():
        return [], "pip-audit not installed"

    cache_root = OUTPUT_ROOT / ".cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["XDG_CACHE_HOME"] = str(cache_root.resolve())

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(req_file),
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    if proc.returncode not in (0, 1):
        return [], proc.stderr or f"pip-audit exit {proc.returncode}"

    if not proc.stdout.strip():
        return [], proc.stderr

    data = json.loads(proc.stdout)
    rows: list[dict[str, Any]] = []
    manifest = str(req_file)

    if isinstance(data, dict) and "dependencies" in data:
        for dep in data["dependencies"]:
            for vuln in dep.get("vulns", []):
                rows.append(
                    {
                        **vuln,
                        "name": dep.get("name"),
                        "version": dep.get("version"),
                        "manifest": manifest,
                    }
                )
    elif isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                row.setdefault("manifest", manifest)
                rows.append(row)

    return rows, proc.stderr


def query_osv_batch(packages: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    """
    Query OSV for a list of ``(name, version, ecosystem)`` tuples.

    Returns flat list of ``{package, version, ecosystem, manifest, vuln}`` dicts.
    Gracefully returns ``[]`` on network/import errors.
    """
    if not packages:
        return []

    queries = [
        {"package": {"name": name, "ecosystem": eco}, "version": ver}
        for name, ver, eco in packages
    ]

    try:
        resp = requests.post(
            OSV_QUERYBATCH_URL,
            json={"queries": queries},
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for (name, ver, eco), result in zip(packages, payload.get("results", [])):
        for vuln in result.get("vulns", []):
            results.append(
                {
                    "package": name,
                    "version": ver,
                    "ecosystem": eco,
                    "vuln": vuln,
                }
            )
    return results


def _vuln_ids(vuln: dict[str, Any]) -> set[str]:
    """Collect canonical ids and aliases for dedupe."""
    ids: set[str] = set()
    vid = vuln.get("id")
    if vid:
        ids.add(str(vid))
    for alias in vuln.get("aliases", []) or []:
        ids.add(str(alias))
    return ids


def _severity_from_osv(vuln: dict[str, Any]) -> str:
    """Map OSV vuln record to low/medium/high/critical."""
    db = vuln.get("database_specific") or {}
    if isinstance(db.get("severity"), str):
        sev = db["severity"].lower()
        if sev in _TIER_ORDER:
            return sev

    for entry in vuln.get("severity", []) or []:
        if not isinstance(entry, dict):
            continue
        score_raw = entry.get("score", "")
        if entry.get("type", "").startswith("CVSS") and score_raw:
            try:
                score_str = str(score_raw).split("/")[0]
                score = float(score_str)
                if score >= 9.0:
                    return "critical"
                if score >= 7.0:
                    return "high"
                if score >= 4.0:
                    return "medium"
                return "low"
            except ValueError:
                pass

    return "medium"


def _severity_from_pip_audit(vuln: dict[str, Any]) -> str:
    """pip-audit rows often lack severity — default medium."""
    for key in ("severity", "level"):
        raw = vuln.get(key)
        if raw:
            sev = str(raw).lower()
            if sev in _TIER_ORDER:
                return sev
    return "medium"


def _merge_vuln_records(
    pip_rows: list[dict[str, Any]],
    osv_hits: list[dict[str, Any]],
    manifests_found: list[str],
) -> list[dict[str, Any]]:
    """
    Combine pip-audit and OSV into normalized vulnerability dicts.

    pip-audit is primary when both report the same id/alias; OSV-only rows use source=osv.
    """
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}

    def _insert_or_update(key: tuple[str, str, str], row: dict[str, Any]) -> None:
        if key not in merged:
            merged[key] = row
            return
        existing = merged[key]
        if row.get("source") == "pip_audit" and existing.get("source") == "osv":
            row["corroborated_by"] = list(set((row.get("corroborated_by") or []) + ["osv"]))
            merged[key] = {**row, **{k: v for k, v in existing.items() if k not in row}}
            merged[key]["source"] = "pip_audit"
            merged[key]["corroborated_by"] = row.get("corroborated_by")
        elif row.get("source") == "osv" and existing.get("source") == "pip_audit":
            corro = list(set((existing.get("corroborated_by") or []) + ["osv"]))
            existing["corroborated_by"] = corro
        else:
            merged[key] = existing

    for row in pip_rows:
        pkg = (row.get("name") or "?").lower()
        ver = row.get("version") or "?"
        vid = row.get("id") or "unknown"
        manifest = row.get("manifest") or manifests_found[0] if manifests_found else "requirements.txt"
        rel_manifest = Path(manifest).name if manifest else "requirements.txt"
        sev = _severity_from_pip_audit(row)
        entry = {
            "package": pkg,
            "version": ver,
            "id": vid,
            "aliases": row.get("aliases") or [],
            "severity": sev,
            "source": "pip_audit",
            "corroborated_by": None,
            "fix_versions": row.get("fix_versions") or [],
            "summary": (row.get("description") or row.get("summary") or "")[:500],
            "manifest": rel_manifest,
        }
        _insert_or_update((pkg, ver, vid), entry)

    for hit in osv_hits:
        vuln = hit.get("vuln") or {}
        pkg = hit.get("package", "?").lower()
        ver = hit.get("version") or "?"
        vid = vuln.get("id") or "unknown"
        sev = _severity_from_osv(vuln)
        ecosystem = hit.get("ecosystem") or "PyPI"
        manifest = hit.get("manifest") or (
            "package.json" if ecosystem == "npm" else "requirements.txt"
        )

        entry = {
            "package": pkg,
            "version": ver,
            "id": vid,
            "aliases": vuln.get("aliases") or [],
            "severity": sev,
            "source": "osv",
            "corroborated_by": None,
            "fix_versions": _fix_versions_from_osv(vuln),
            "summary": (vuln.get("summary") or "")[:500],
            "manifest": manifest,
        }

        matched_key: tuple[str, str, str] | None = None
        osv_ids = _vuln_ids(vuln)
        for key, existing in merged.items():
            existing_ids = {existing.get("id", "")} | set(existing.get("aliases") or [])
            if osv_ids & existing_ids:
                matched_key = key
                break

        if matched_key:
            existing = merged[matched_key]
            corro = list(set((existing.get("corroborated_by") or []) + ["osv"]))
            existing["corroborated_by"] = corro
            if _TIER_ORDER.get(sev, 0) > _TIER_ORDER.get(existing.get("severity", "low"), 0):
                existing["severity"] = sev
            if not existing.get("summary") and entry.get("summary"):
                existing["summary"] = entry["summary"]
            if not existing.get("fix_versions") and entry.get("fix_versions"):
                existing["fix_versions"] = entry["fix_versions"]
        else:
            _insert_or_update((pkg, ver, vid), entry)

    return list(merged.values())


def _fix_versions_from_osv(vuln: dict[str, Any]) -> list[str]:
    """Extract fixed versions from OSV affected ranges."""
    fixes: list[str] = []
    for affected in vuln.get("affected", []) or []:
        for item in affected.get("ranges", []) or []:
            for event in item.get("events", []) or []:
                if "fixed" in event:
                    fixes.append(str(event["fixed"]))
    return fixes


def run_dependency_scan(model_dir: Path) -> dict[str, Any] | None:
    """
    Run pip-audit + OSV on manifests in ``model_dir``.

    Returns ``None`` when no dependency manifests exist; otherwise a summary dict
    for ``tool_results["dependencies"]``.
    """
    manifests = find_requirement_files(model_dir)
    if not manifests:
        return None

    manifests_found = [m["path"] for m in manifests]
    pip_rows: list[dict[str, Any]] = []
    osv_packages: list[tuple[str, str, str, str]] = []  # name, ver, eco, manifest

    for manifest in manifests:
        rel = manifest["path"]
        kind = manifest["kind"]
        full = model_dir / rel

        if kind == "requirements":
            rows, _ = run_pip_audit(full)
            for row in rows:
                row["manifest"] = rel
            pip_rows.extend(rows)
            for name, ver, eco in _parse_requirements_pins(full):
                osv_packages.append((name, ver, eco, rel))

        elif kind == "pyproject":
            text = full.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'["\']([a-zA-Z0-9][a-zA-Z0-9._\-]*)["\']\s*=\s*["\']([^"\']+)["\']', text):
                name, ver = m.group(1), m.group(2)
                if re.match(r"^\d", ver) or ver[0].isdigit():
                    osv_packages.append((name.lower(), ver, "PyPI", rel))

        elif kind == "package_json":
            try:
                data = json.loads(full.read_text(encoding="utf-8"))
                for section in ("dependencies", "devDependencies"):
                    for name, ver in (data.get(section) or {}).items():
                        ver_clean = ver.lstrip("^~>=<!")
                        if ver_clean and ver_clean[0].isdigit():
                            osv_packages.append((name.lower(), ver_clean.split()[0], "npm", rel))
            except (json.JSONDecodeError, OSError):
                pass

        elif kind == "go_mod":
            text = full.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"^\s*([\w.\-/]+)\s+v([\d][^\s]+)", text, re.MULTILINE):
                osv_packages.append((m.group(1), m.group(2), "Go", rel))

    osv_query_list = [(n, v, e) for n, v, e, _ in osv_packages]
    osv_hits_raw = query_osv_batch(osv_query_list)
    osv_hits: list[dict[str, Any]] = []
    for hit in osv_hits_raw:
        pkg = hit.get("package", "")
        ver = hit.get("version", "")
        eco = hit.get("ecosystem", "PyPI")
        manifest = "requirements.txt"
        for n, v, e, m in osv_packages:
            if n == pkg and v == ver and e == eco:
                manifest = m
                break
        osv_hits.append({**hit, "manifest": manifest})

    vulnerabilities = _merge_vuln_records(pip_rows, osv_hits, manifests_found)

    by_severity: dict[str, int] = {}
    for v in vulnerabilities:
        sev = (v.get("severity") or "medium").lower()
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return {
        "manifests_found": manifests_found,
        "vuln_count": len(vulnerabilities),
        "vulnerabilities": vulnerabilities[:100],
        "by_severity": by_severity,
        "pip_audit_available": _pip_audit_available(),
        "pip_audit_vuln_count": len(pip_rows),
        "osv_vuln_count": len(osv_hits),
        "scan_mode": "pip_audit_plus_osv",
    }


def dependency_tier(summary: dict[str, Any] | None) -> str:
    """Worst severity tier among dependency vulnerabilities."""
    if not summary or not summary.get("vuln_count"):
        return "low"
    worst = "low"
    for v in summary.get("vulnerabilities") or []:
        sev = (v.get("severity") or "medium").lower()
        if sev in _TIER_ORDER and _TIER_ORDER[sev] > _TIER_ORDER[worst]:
            worst = sev
    for sev, count in (summary.get("by_severity") or {}).items():
        if count and sev in _TIER_ORDER and _TIER_ORDER[sev] > _TIER_ORDER[worst]:
            worst = sev
    return worst
