"""
Pure transforms for benchmark result files — no DB, no frontend imports.

Mirrors detection/summary logic in frontend/benchmark_data.py so ingest rows
match what the UI shows.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_STEM_TS_RE = re.compile(
    r"^(\d{8}T\d{6}Z)_([a-z0-9_]+)_(.+)$", re.IGNORECASE
)


def _parse_iso_timestamp(value: str | None) -> str | None:
    if not value or value == "—":
        return None
    raw = value.strip()
    for candidate in (raw, raw.replace("Z", "+00:00")):
        try:
            datetime.fromisoformat(candidate)
            return raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        except ValueError:
            continue
    for fmt in ("%Y%m%d_%H%M%S", "%Y%m%dT%H%M%SZ"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.isoformat() + "+00:00"
        except ValueError:
            continue
    return None


def parse_completed_at(path: Path, data: dict[str, Any] | None, rows: list[dict] | None) -> str | None:
    """Best-effort completed_at from JSON timestamp or file stem."""
    if data is not None:
        ts = data.get("timestamp") or data.get("ts")
        parsed = _parse_iso_timestamp(ts if isinstance(ts, str) else None)
        if parsed:
            return parsed
    if rows:
        ts = rows[0].get("ts") or rows[0].get("timestamp")
        parsed = _parse_iso_timestamp(ts if isinstance(ts, str) else None)
        if parsed:
            return parsed
    m = _STEM_TS_RE.match(path.stem)
    if m:
        return _parse_iso_timestamp(m.group(1))
    return None


def detect_kind(path: Path) -> str | None:
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
        if "per_subject" in obj and isinstance(obj.get("summary"), dict):
            if "accuracy" in obj["summary"]:
                return "mmlu"
        results = obj.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                if "task_id" in first and ("generated_code" in first or "tests_passed" in first):
                    return "mbpp"
                if "question_type" in first:
                    return "tomi"
                if "article_id" in first and "options" in first:
                    return "quality"
        summary = obj.get("summary") or {}
        if isinstance(summary, dict) and "hard_accuracy" in summary:
            return "quality"
        if "hard_only" in obj:
            return "quality"
        metrics = obj.get("metrics") or obj.get("summary") or {}
        if isinstance(metrics, dict) and "accuracy" in metrics and "responses" in obj:
            return "truthfulqa"
    except Exception:
        return None
    return None


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def read_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _headline_truthfulqa(data: dict[str, Any]) -> tuple[str, float | None, int]:
    metrics = data.get("metrics") or data.get("summary") or {}
    acc = metrics.get("accuracy")
    n = metrics.get("total_evaluated") or len(data.get("responses") or [])
    return "accuracy", float(acc) if acc is not None else None, int(n)


def _headline_mmlu(data: dict[str, Any]) -> tuple[str, float | None, int]:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    n = summary.get("total") or len(data.get("results") or [])
    return "accuracy", float(acc) if acc is not None else None, int(n)


def _headline_tomi(data: dict[str, Any]) -> tuple[str, float | None, int]:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    n = summary.get("total") or len(data.get("results") or [])
    return "accuracy", float(acc) if acc is not None else None, int(n)


def _headline_consistency(data: dict[str, Any]) -> tuple[str, float | None, int]:
    summary = data.get("summary") or {}
    mean_f1 = summary.get("mean_f1_overall")
    n = summary.get("total_questions") or len(data.get("questions") or [])
    return "mean_f1", float(mean_f1) if mean_f1 is not None else None, int(n)


def _headline_ifeval(rows: list[dict[str, Any]]) -> tuple[str, float | None, int]:
    if not rows:
        return "pass_rate", None, 0
    passed = sum(1 for r in rows if (r.get("judge") or {}).get("passed"))
    n = len(rows)
    rate = passed / n if n else None
    return "pass_rate", float(rate) if rate is not None else None, n


def _headline_mbpp(data: dict[str, Any]) -> tuple[str, float | None, int]:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    n = summary.get("total") or len(data.get("results") or [])
    return "accuracy", float(acc) if acc is not None else None, int(n)


def _headline_quality(data: dict[str, Any]) -> tuple[str, float | None, int]:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    n = summary.get("total_questions") or len(data.get("results") or [])
    return "accuracy", float(acc) if acc is not None else None, int(n)


def extract_metrics(kind: str, data: dict[str, Any] | None, rows: list[dict] | None) -> dict[str, Any]:
    if kind == "ifeval" and rows:
        passed = sum(1 for r in rows if (r.get("judge") or {}).get("passed"))
        return {"passed": passed, "total": len(rows)}
    if data is None:
        return {}
    if kind == "truthfulqa":
        metrics = data.get("metrics") or data.get("summary") or {}
        return {
            "summary": metrics,
            "correct": metrics.get("correct"),
            "total_evaluated": metrics.get("total_evaluated"),
        }
    if kind == "mmlu":
        return {
            "summary": data.get("summary") or {},
            "per_subject": data.get("per_subject") or {},
        }
    if kind == "consistency":
        return {"summary": data.get("summary") or {}}
    if kind == "tomi":
        return {"summary": data.get("summary") or {}}
    if kind == "mbpp":
        return {"summary": data.get("summary") or {}}
    if kind == "quality":
        summary = data.get("summary") or {}
        return {
            "summary": summary,
            "hard_accuracy": summary.get("hard_accuracy"),
            "hard_questions": summary.get("hard_questions"),
        }
    return {}


def extract_items(kind: str, data: dict[str, Any] | None, rows: list[dict] | None) -> list[Any]:
    if kind == "ifeval":
        return rows or []
    if data is None:
        return []
    if kind == "truthfulqa":
        return data.get("responses") or []
    if kind in ("mmlu", "tomi", "mbpp", "quality"):
        return data.get("results") or []
    if kind == "consistency":
        return data.get("questions") or []
    return []


def gateway_model_id(kind: str, data: dict[str, Any] | None, rows: list[dict] | None) -> str | None:
    del kind
    if rows:
        model = rows[0].get("model")
        if isinstance(model, str) and model.strip() and model != "—":
            return model.strip()
    if data is not None:
        model = data.get("model")
        if isinstance(model, str) and model.strip() and model != "—":
            return model.strip()
    return None


def benchmark_run_row(path: Path) -> dict[str, Any] | None:
    """One ``benchmark_runs`` row from a result file, or None if unparseable."""
    if path.suffix == ".log":
        return None
    kind = detect_kind(path)
    if kind is None:
        return None

    data: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None

    if kind == "ifeval":
        rows = read_jsonl_rows(path)
        if not rows:
            return None
        headline_metric, headline_value, n_items = _headline_ifeval(rows)
    else:
        data = read_json_file(path)
        if data is None:
            return None
        if kind == "truthfulqa":
            metrics = data.get("metrics") or data.get("summary") or {}
            if not metrics.get("total_evaluated") and not data.get("responses"):
                return None
            headline_metric, headline_value, n_items = _headline_truthfulqa(data)
        elif kind == "consistency":
            headline_metric, headline_value, n_items = _headline_consistency(data)
        elif kind == "mmlu":
            headline_metric, headline_value, n_items = _headline_mmlu(data)
        elif kind == "tomi":
            headline_metric, headline_value, n_items = _headline_tomi(data)
        elif kind == "mbpp":
            headline_metric, headline_value, n_items = _headline_mbpp(data)
        elif kind == "quality":
            headline_metric, headline_value, n_items = _headline_quality(data)
        else:
            return None

    model = gateway_model_id(kind, data, rows)
    if not model:
        return None

    completed_at = parse_completed_at(path, data, rows)
    run_params = data.get("run_params") if data else None
    if run_params is None and data and data.get("hard_only") is not None:
        run_params = {"hard_only": data.get("hard_only")}

    return {
        "model_id": None,
        "output_slug": path.stem,
        "source_filename": path.name,
        "gateway_model_id": model,
        "benchmark_key": kind,
        "inference_backend": (data or {}).get("inference_backend") or "gateway",
        "status": (data or {}).get("status") or "complete",
        "headline_metric": headline_metric,
        "headline_value": headline_value,
        "n_items": n_items,
        "metrics": extract_metrics(kind, data, rows),
        "items": extract_items(kind, data, rows),
        "run_params": run_params,
        "started_at": None,
        "completed_at": completed_at,
        "visibility": "public",
        "owner_user_id": None,
        "config_fingerprint": None,
        "config_json": {},
    }
