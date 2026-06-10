"""
Data source for /benchmarks and /benchmarks/<slug>.

Reads Jack's benchmark-track outputs from testing/basic_tests/test_results/
(falls back to test_results/ at the repo root). Three benchmark types,
three slightly different schemas — detected by file content, not name,
so a rename doesn't break the viewer.

Status: built against Jack's CURRENT output formats (snapshot 2026-06-05).
If schemas change, _detect_kind() + _summarize_*() are the seams to update.

TruthfulQA (tqa_test.py):
    {model, timestamp, metrics: {accuracy, correct, total_evaluated, ...},
     responses: [...]}

IFEval (if_test.py):
    JSONL — one row per question, each row has {key, prompt, response,
    instruction_id_list, judge: {passed: bool, ...}, ts}

Consistency (consistency_test.py):
    {model, timestamp, summary: {total_questions, mean_f1_overall},
     questions: [...]}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).parent.parent
PRIMARY_DIR = ROOT / "testing" / "basic_tests" / "test_results"
FALLBACK_DIR = ROOT / "test_results"


def _candidate_dirs() -> list[Path]:
    return [d for d in (PRIMARY_DIR, FALLBACK_DIR) if d.is_dir()]


def _format_ts(raw: str) -> str:
    """Human-readable timestamp from either 'YYYYMMDD_HHMMSS' or ISO 8601."""
    if not raw:
        return "—"
    for fmt in ("%Y%m%d_%H%M%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return raw[:19] if len(raw) > 19 else raw


def _detect_kind(path: Path) -> str | None:
    """Return 'truthfulqa' | 'ifeval' | 'consistency' | None.

    Uses content shape, not filename, so renamed files still resolve.
    """
    try:
        if path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                line = f.readline()
            obj = json.loads(line) if line.strip() else {}
            if isinstance(obj, dict) and "judge" in obj and "instruction_id_list" in obj:
                return "ifeval"
            return None
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return None
        if "summary" in obj and "mean_f1_overall" in (obj.get("summary") or {}):
            return "consistency"
        if "metrics" in obj and isinstance(obj["metrics"], dict) and "accuracy" in obj["metrics"]:
            return "truthfulqa"
    except Exception:
        return None
    return None


def _summarize_truthfulqa(path: Path, data: dict) -> dict:
    metrics = data.get("metrics") or {}
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "truthfulqa",
        "kind_label": "TruthfulQA",
        "model": data.get("model") or "—",
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "headline_metric": "accuracy",
        "headline_value": metrics.get("accuracy"),
        "headline_display": f"{metrics.get('accuracy', 0):.1%}" if metrics.get("accuracy") is not None else "—",
        "n": metrics.get("total_evaluated") or len(data.get("responses") or []),
        "extras": {
            "correct": metrics.get("correct"),
            "total_evaluated": metrics.get("total_evaluated"),
        },
    }


def _summarize_consistency(path: Path, data: dict) -> dict:
    summary = data.get("summary") or {}
    mean_f1 = summary.get("mean_f1_overall")
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "consistency",
        "kind_label": "Consistency",
        "model": data.get("model") or "—",
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "headline_metric": "mean F1",
        "headline_value": mean_f1,
        "headline_display": f"{mean_f1:.3f}" if mean_f1 is not None else "—",
        "n": summary.get("total_questions") or len(data.get("questions") or []),
        "extras": {},
    }


def _summarize_ifeval(path: Path) -> dict:
    """IFEval is JSONL — every row is one question; we aggregate here."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return {
            "slug": path.stem,
            "filename": path.name,
            "kind": "ifeval",
            "kind_label": "IFEval",
            "model": "—",
            "timestamp_raw": "",
            "timestamp": "—",
            "headline_metric": "pass rate",
            "headline_value": None,
            "headline_display": "—",
            "n": 0,
            "extras": {},
        }
    passed = sum(1 for r in rows if (r.get("judge") or {}).get("passed"))
    n = len(rows)
    rate = passed / n if n else None
    # Model isn't recorded per-row in this schema; pull from filename suffix
    # or leave as "—" until Jack standardizes.
    ts_raw = rows[0].get("ts") or ""
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "ifeval",
        "kind_label": "IFEval",
        "model": "—  (not in JSONL schema)",
        "timestamp_raw": ts_raw,
        "timestamp": _format_ts(ts_raw),
        "headline_metric": "pass rate",
        "headline_value": rate,
        "headline_display": f"{rate:.1%}" if rate is not None else "—",
        "n": n,
        "extras": {"passed": passed, "total": n},
    }


def _summarize_file(path: Path) -> dict | None:
    kind = _detect_kind(path)
    if kind is None:
        return None
    if kind == "ifeval":
        return _summarize_ifeval(path)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if kind == "truthfulqa":
        return _summarize_truthfulqa(path, data)
    if kind == "consistency":
        return _summarize_consistency(path, data)
    return None


def get_benchmarks_data() -> dict:
    """Return per-file aggregate rows for every benchmark output on disk."""
    dirs = _candidate_dirs()
    if not dirs:
        return {
            "has_runs": False,
            "search_paths": [str(PRIMARY_DIR), str(FALLBACK_DIR)],
            "runs": [],
            "kinds": [],
        }
    rows: list[dict] = []
    for d in dirs:
        for path in sorted(list(d.glob("*.json")) + list(d.glob("*.jsonl"))):
            row = _summarize_file(path)
            if row:
                rows.append(row)
    # most recent first
    rows.sort(key=lambda r: r["timestamp_raw"], reverse=True)
    kinds = sorted({r["kind_label"] for r in rows})
    return {
        "has_runs": bool(rows),
        "search_paths": [str(d) for d in dirs],
        "runs": rows,
        "kinds": kinds,
    }


def get_benchmark_detail(slug: str) -> dict | None:
    """Full payload for one benchmark file. Returns None if not found."""
    # slug comes straight from the URL — refuse anything that could
    # traverse outside the benchmark dirs before touching the filesystem.
    if not is_safe_slug(slug):
        return None
    for d in _candidate_dirs():
        candidate_paths = [d / f"{slug}.json", d / f"{slug}.jsonl"]
        for path in candidate_paths:
            if path.is_file():
                kind = _detect_kind(path)
                if kind is None:
                    continue
                if kind == "ifeval":
                    rows = []
                    with path.open("r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rows.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                    summary = _summarize_ifeval(path)
                    summary["raw_rows"] = rows[:50]  # cap table size
                    summary["raw_row_count"] = len(rows)
                    return summary
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if kind == "truthfulqa":
                    summary = _summarize_truthfulqa(path, data)
                    summary["responses"] = (data.get("responses") or [])[:50]
                    summary["raw_row_count"] = len(data.get("responses") or [])
                    return summary
                if kind == "consistency":
                    summary = _summarize_consistency(path, data)
                    summary["questions"] = (data.get("questions") or [])[:50]
                    summary["raw_row_count"] = len(data.get("questions") or [])
                    return summary
    return None
