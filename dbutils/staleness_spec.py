"""Dynamic per-pillar spec baselines for staleness checks.

Each pillar compares a run against the **current** tooling/spec on disk (scanner
version, garak probe_spec, eval suite files, benchmark runner scripts) instead of
a global calendar cutoff.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from dbutils.env import REPO_ROOT

_SCAN_TOOL_ROWS = (
    ("modelscan", "ModelScan", "badge-scan"),
    ("fickling", "Fickling", "badge-scan"),
    ("modelaudit", "ModelAudit", "badge-scan"),
    ("dependencies", "Dependencies", "badge-scan"),
    ("secrets", "Secrets", "badge-scan"),
)
_SCAN_TOOLS = tuple(key for key, _, _ in _SCAN_TOOL_ROWS)
_SCAN_SKIP_KEYS = {
    "modelscan": "skip_modelscan",
    "fickling": "skip_fickling",
    "modelaudit": "skip_modelaudit",
    "dependencies": "skip_deps",
    "secrets": "skip_secrets",
}


SCAN_TOOL_ROWS = _SCAN_TOOL_ROWS


def scan_tool_ids() -> tuple[str, ...]:
    """Canonical scanner tool keys for list views and staleness checks."""
    return _SCAN_TOOLS

_PICKLE_SUFFIXES = (".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt")
_MANIFEST_MARKERS = (
    "requirements",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "environment.yml",
)


def scan_tool_applicability(scanned_files: list[Any] | None) -> dict[str, bool]:
    """Whether each scan tool could have produced results for this artifact set."""
    files = [str(f).lower() for f in (scanned_files or [])]
    has_pickle = any(
        any(name.endswith(suffix) for suffix in _PICKLE_SUFFIXES) for name in files
    )
    has_manifest = any(
        any(marker in name for marker in _MANIFEST_MARKERS) for name in files
    )
    return {
        "modelscan": True,
        "modelaudit": True,
        "secrets": True,
        "fickling": has_pickle,
        "dependencies": has_manifest,
    }


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return _sha256_hex(path.read_bytes().decode("utf-8", errors="replace"))


def _scan_enabled_tools(config: dict[str, Any]) -> tuple[str, ...]:
    """Scanners expected to have run given a normalized scan config_json."""
    enabled: list[str] = []
    for tool, skip_key in _SCAN_SKIP_KEYS.items():
        if not config.get(skip_key):
            enabled.append(tool)
    return tuple(enabled)


def current_scanner_version() -> str:
    import scanner

    return scanner.__version__


def scan_staleness_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("scanned_file_count", 0) == 0:
        reasons.append("0 files scanned")

    status = (row.get("status") or "").lower()
    if status not in ("complete", "completed", "unknown", ""):
        reasons.append(f"status is {row.get('status')}")

    run_ver = row.get("scanner_version")
    current_ver = current_scanner_version()
    if run_ver and run_ver not in ("—", "", None) and run_ver != current_ver:
        reasons.append(f"scanner version {run_ver} != current {current_ver}")

    config = row.get("config_json") if isinstance(row.get("config_json"), dict) else {}
    expected_tools = _scan_enabled_tools(config)
    tool_status = row.get("tool_status") or {}
    applicability = row.get("tool_applicability") or {}
    for tool in expected_tools:
        if applicability and not applicability.get(tool, True):
            continue
        if tool not in tool_status:
            reasons.append(f"missing scanner: {tool}")

    return reasons


def current_safety_garak_probe_spec() -> str:
    from safety.garak.report_validation import DEFAULT_PROBE_SPEC

    return DEFAULT_PROBE_SPEC


def garak_probe_spec_digest(probe_spec: str) -> str:
    return _sha256_hex(probe_spec.strip())


def expected_garak_module_count(probe_spec: str | None = None) -> int:
    from safety.garak.report_validation import expected_module_count

    spec = (probe_spec or "").strip() or current_safety_garak_probe_spec()
    if not spec:
        return 0
    return expected_module_count(spec)


def safety_staleness_reasons(row: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if row.get("missing_suites"):
        reasons.append(f"missing suites: {', '.join(row['missing_suites'])}")

    status = (row.get("status") or "").lower()
    if status not in ("complete", "completed", ""):
        reasons.append(f"status is {row.get('status')}")

    config = row.get("config_json") if isinstance(row.get("config_json"), dict) else {}
    skip_garak = bool(config.get("skip_garak"))
    garak_probes = (config.get("garak_probes") or "").strip()

    if skip_garak:
        return reasons

    current_spec = current_safety_garak_probe_spec()
    run_spec = garak_probes or current_spec
    expected = expected_garak_module_count(run_spec)

    stored_digest = row.get("garak_probe_spec_digest") or config.get("garak_probe_spec_digest")
    current_digest = garak_probe_spec_digest(current_spec)
    if stored_digest and stored_digest != current_digest and not garak_probes:
        reasons.append("garak probe set changed since run")

    garak_count = row.get("garak_probe_count")
    if garak_count is not None and expected and garak_count < expected:
        reasons.append(f"garak modules {garak_count} < expected {expected}")

    return reasons


def _eval_suite_cfg(suite_key: str) -> dict[str, Path] | None:
    from frontend.eval_launch import SUITES

    raw = SUITES.get(suite_key)
    if not raw:
        return None
    return {
        "suite": Path(raw["suite"]),
        "rubric": Path(raw["rubric"]),
        "system_prompt": Path(raw["system_prompt"]),
    }


def _read_yaml_field(path: Path, field: str) -> str | None:
    """Read a top-level scalar from a YAML file without importing heavy deps at startup."""
    if not path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    val = data.get(field)
    return str(val).strip() if val is not None else None


def _rubric_dimension_keys(path: Path) -> list[str]:
    """Dimension ids defined in a rubric YAML (including shared refs by key name)."""
    if not path.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    dims = data.get("dimensions")
    if isinstance(dims, dict):
        return list(dims.keys())
    return []


def current_eval_suite_file_digests(suite_key: str) -> dict[str, str] | None:
    """SHA-256 digests of suite/rubric/system_prompt files at read time."""
    cfg = _eval_suite_cfg(suite_key)
    if not cfg:
        return None
    out: dict[str, str] = {}
    for label, path in cfg.items():
        digest = _file_digest(path)
        if digest is None:
            return None
        out[label] = digest
    return out


def current_eval_suite_versions(suite_key: str) -> dict[str, str] | None:
    cfg = _eval_suite_cfg(suite_key)
    if not cfg:
        return None
    rubric_version = _read_yaml_field(cfg["rubric"], "rubric_version")
    return {
        "suite": suite_key,
        "rubric_version": rubric_version or cfg["rubric"].stem,
        "system_prompt_version": cfg["system_prompt"].stem,
    }


def eval_staleness_reasons(row: dict[str, Any]) -> list[str]:
    from frontend.eval_launch import SUITES

    reasons: list[str] = []
    suite = (row.get("suite") or row.get("suite_version") or "").strip()
    if not suite:
        return reasons

    if suite.startswith("custom_"):
        return reasons

    if suite not in SUITES:
        reasons.append(f"suite {suite!r} is not a current curated suite")
        return reasons

    # Execution-scored suites (text-to-SQL/JSON/numeric/tool-use) are graded by
    # RUNNING the answer, not an LLM judge. They carry an inert placeholder
    # rubric that the runner never loads, and their rows have no judge
    # dimensions. Applying the rubric-version and rubric-dimension checks below
    # would flag EVERY execution run stale forever (the placeholder's version /
    # dims never match the run's), so skip them — only the suite version, the
    # suite file, and the system prompt are meaningful here.
    is_execution = SUITES.get(suite, {}).get("scoring") == "execution"

    current = current_eval_suite_versions(suite)
    if not current:
        return reasons

    for field, current_val in current.items():
        if field == "suite":
            continue
        if is_execution and field == "rubric_version":
            continue  # inert placeholder rubric — meaningless for execution
        run_val = row.get(field)
        if run_val and run_val != current_val:
            reasons.append(f"{field} changed ({run_val} → {current_val})")

    cfg = _eval_suite_cfg(suite)
    if cfg:
        stored_digests = row.get("eval_suite_file_digests")
        config = row.get("config_json") if isinstance(row.get("config_json"), dict) else {}
        if not isinstance(stored_digests, dict):
            stored_digests = config.get("eval_suite_file_digests")
        current_digests = current_eval_suite_file_digests(suite)
        if isinstance(stored_digests, dict) and current_digests:
            for label, digest in current_digests.items():
                if is_execution and label == "rubric":
                    continue
                run_digest = stored_digests.get(label)
                if run_digest and run_digest != digest:
                    reasons.append(f"suite file {label} changed since run")
        for label, path in cfg.items():
            if is_execution and label == "rubric":
                continue
            if _file_digest(path) is None:
                reasons.append(f"suite file missing: {path.name}")

        if not is_execution:
            expected_dims = _rubric_dimension_keys(cfg["rubric"])
            dim_means = row.get("dim_means") or {}
            if isinstance(dim_means, dict) and expected_dims:
                missing = [
                    d for d in expected_dims
                    if dim_means.get(d) is None
                ]
                if missing:
                    reasons.append(
                        f"missing rubric dimensions: {', '.join(missing)}"
                    )
    return reasons


def current_benchmark_spec_digest(benchmark_key: str) -> str | None:
    from benchmarks.run_benchmark import BENCHMARKS

    cfg = BENCHMARKS.get(benchmark_key)
    if not cfg:
        return None
    script = REPO_ROOT / "benchmarks" / cfg["script"]
    script_digest = _file_digest(script)
    if script_digest is None:
        return None
    payload = {
        "benchmark_key": benchmark_key,
        "script": script_digest,
        "sample": cfg.get("sample"),
        "seed": cfg.get("seed"),
    }
    return _sha256_hex(json.dumps(payload, sort_keys=True))


def benchmark_staleness_reasons(row: dict[str, Any]) -> list[str]:
    from benchmarks.run_benchmark import BENCHMARKS
    from frontend.benchmark_data import is_reference_slug

    slug = row.get("slug") or ""
    if is_reference_slug(slug):
        return []

    reasons: list[str] = []
    kind = row.get("kind") or row.get("benchmark_key") or ""
    if kind and kind not in BENCHMARKS:
        reasons.append(f"benchmark {kind!r} is not current")

    if kind in BENCHMARKS:
        current_digest = current_benchmark_spec_digest(kind)
        run_digest = row.get("benchmark_spec_digest")
        if current_digest and run_digest and run_digest != current_digest:
            reasons.append(f"benchmark {kind} definition changed since run")

    return reasons
