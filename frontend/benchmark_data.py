"""
Data source for /benchmarks and /benchmarks/<slug>.

Reads public benchmark outputs from benchmarks/results/
(legacy fallbacks: testing/basic_tests/test_results/, test_results/).
Schema detection is content-based so renames do not break the viewer.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).parent.parent
PRIMARY_DIR = ROOT / "benchmarks" / "results"
LEGACY_DIRS = (
    ROOT / "testing" / "basic_tests" / "test_results",
    ROOT / "test_results",
)

# Context shown on benchmark detail pages (about, field glossary, how to read scores).
BENCHMARK_META: dict[str, dict] = {
    "truthfulqa": {
        "title": "TruthfulQA",
        "about": (
            "Multiple-choice factuality benchmark. Each question has several answer options; "
            "the model must pick the letter for the most truthful answer. Measures whether "
            "the model avoids common misconceptions and hedging traps."
        ),
        "source": "https://github.com/sylinrl/TruthfulQA",
        "fields": [
            ("accuracy", "Fraction of questions where the model's letter matches the correct option."),
            ("correct_letter", "The letter (A–D) of the best truthful answer for this question."),
            ("model_answer", "Letter the model chose. Mismatch with correct_letter counts as wrong."),
            ("answer_text", "Full text of the model's chosen option, when recorded."),
        ],
        "item_label": "question",
    },
    "ifeval": {
        "title": "IFEval",
        "about": (
            "Instruction-following benchmark with verifiable constraints (e.g. \"no commas\", "
            "\"exactly N sentences\"). Each prompt lists instruction IDs; an automated judge "
            "checks whether the model's response satisfies every constraint."
        ),
        "source": "https://github.com/google-research/google-research/tree/master/instruction_following_eval",
        "fields": [
            ("pass rate", "Fraction of prompts where all constraints were satisfied."),
            ("instruction_id_list", "Constraint types applied to this prompt (IFEval registry IDs)."),
            ("judge.passed", "True when every instruction in the list passed for this response."),
            ("judge.per_instruction", "Per-constraint pass/fail breakdown inside the expanded row."),
            ("response", "Raw model completion judged against the constraints."),
        ],
        "item_label": "prompt",
    },
    "consistency": {
        "title": "Consistency (rephrasing)",
        "about": (
            "Robustness check: the same underlying question is asked in several paraphrases. "
            "BERTScore F1 compares response pairs — high mean F1 means the model gives "
            "semantically similar answers regardless of wording."
        ),
        "source": "Custom pilot (BERTScore)",
        "fields": [
            ("mean F1", "Average BERTScore F1 across all paraphrase pairs for one topic (0–1)."),
            ("mean_f1_overall", "Run headline: mean of per-question mean F1 scores."),
            ("paraphrases", "Different wordings of the same question sent to the model."),
            ("responses", "One model completion per paraphrase."),
            ("bertscore.pairs", "Pairwise F1 between responses; lower pairs drag down the mean."),
        ],
        "item_label": "topic",
    },
    "mmlu": {
        "title": "MMLU",
        "about": (
            "Massive Multitask Language Understanding — multiple-choice questions across "
            "57 academic subjects. This pilot samples a subset by default (see runner env "
            "MMLU_SAMPLE). Overall accuracy is correct / total."
        ),
        "source": "https://github.com/hendrycks/test",
        "fields": [
            ("accuracy", "Overall or per-subject fraction of questions answered correctly."),
            ("subject", "MMLU subject area (e.g. college_physics, moral_scenarios)."),
            ("choices", "Four options A–D shown to the model."),
            ("correct_answer", "Letter of the right option."),
            ("model_answer", "Letter the model picked."),
        ],
        "item_label": "question",
    },
    "tomi": {
        "title": "ToMi (theory of mind)",
        "about": (
            "Theory-of-mind stories: characters move objects while others are absent. "
            "Questions test whether the model tracks beliefs vs. reality (first-order, "
            "second-order, memory, etc.)."
        ),
        "source": "https://github.com/facebookresearch/ToMi",
        "fields": [
            ("accuracy", "Fraction of stories answered correctly."),
            ("question_type", "Story probe type: memory, first_order, second_order, reality, …"),
            ("story", "Narrative setup — who entered, moved objects, left."),
            ("correct_answer", "Expected short answer from the story logic."),
            ("model_answer", "What the model returned."),
        ],
        "item_label": "story",
    },
}


def _candidate_dirs() -> list[Path]:
    dirs = [PRIMARY_DIR] if PRIMARY_DIR.is_dir() else []
    for d in LEGACY_DIRS:
        if d.is_dir() and d not in dirs:
            dirs.append(d)
    return dirs


def _format_ts(raw: str) -> str:
    if not raw:
        return "—"
    for fmt in ("%Y%m%d_%H%M%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    return raw[:19] if len(raw) > 19 else raw


def _detect_kind(path: Path) -> str | None:
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
            if isinstance(first, dict) and "question_type" in first:
                return "tomi"
        metrics = obj.get("metrics") or obj.get("summary") or {}
        if isinstance(metrics, dict) and "accuracy" in metrics:
            return "truthfulqa"
    except Exception:
        return None
    return None


def _summarize_truthfulqa(path: Path, data: dict) -> dict:
    metrics = data.get("metrics") or data.get("summary") or {}
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


def _summarize_mmlu(path: Path, data: dict) -> dict:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "mmlu",
        "kind_label": "MMLU",
        "model": data.get("model") or "—",
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "headline_metric": "accuracy",
        "headline_value": acc,
        "headline_display": f"{acc:.1%}" if acc is not None else "—",
        "n": summary.get("total") or len(data.get("results") or []),
        "extras": {"subjects": len(data.get("per_subject") or {})},
    }


def _summarize_tomi(path: Path, data: dict) -> dict:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "tomi",
        "kind_label": "ToMi",
        "model": data.get("model") or "—",
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "headline_metric": "accuracy",
        "headline_value": acc,
        "headline_display": f"{acc:.1%}" if acc is not None else "—",
        "n": summary.get("total") or len(data.get("results") or []),
        "extras": {},
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
    model = rows[0].get("model") or "—"
    ts_raw = rows[0].get("ts") or ""
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "ifeval",
        "kind_label": "IFEval",
        "model": model,
        "timestamp_raw": ts_raw,
        "timestamp": _format_ts(ts_raw),
        "headline_metric": "pass rate",
        "headline_value": rate,
        "headline_display": f"{rate:.1%}" if rate is not None else "—",
        "n": n,
        "extras": {"passed": passed, "total": n},
    }


def _summarize_file(path: Path) -> dict | None:
    if path.suffix == ".log":
        return None
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
        metrics = data.get("metrics") or data.get("summary") or {}
        if not metrics.get("total_evaluated") and not data.get("responses"):
            return None
        return _summarize_truthfulqa(path, data)
    if kind == "consistency":
        return _summarize_consistency(path, data)
    if kind == "mmlu":
        return _summarize_mmlu(path, data)
    if kind == "tomi":
        return _summarize_tomi(path, data)
    return None


def _attach_meta(summary: dict) -> dict:
    """Add benchmark context block for the detail template."""
    kind = summary.get("kind")
    summary["meta"] = BENCHMARK_META.get(kind, {})
    return summary


def get_benchmarks_data() -> dict:
    dirs = _candidate_dirs()
    if not dirs:
        return {
            "has_runs": False,
            "search_paths": [str(PRIMARY_DIR), *[str(d) for d in LEGACY_DIRS]],
            "runs": [],
            "kinds": [],
            "models": [],
        }
    rows: list[dict] = []
    seen: set[str] = set()
    for d in dirs:
        for path in sorted(list(d.glob("*.json")) + list(d.glob("*.jsonl"))):
            if path.stem in seen:
                continue
            row = _summarize_file(path)
            if row:
                seen.add(path.stem)
                rows.append(row)
    rows.sort(key=lambda r: r["timestamp_raw"], reverse=True)
    kinds = sorted({r["kind_label"] for r in rows})
    models = sorted({r["model"] for r in rows if r["model"] and not r["model"].startswith("—")})
    return {
        "has_runs": bool(rows),
        "search_paths": [str(d) for d in dirs],
        "runs": rows,
        "kinds": kinds,
        "models": models,
    }


def get_benchmark_detail(slug: str) -> dict | None:
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
                    summary["raw_rows"] = rows[:50]
                    summary["raw_row_count"] = len(rows)
                    return _attach_meta(summary)
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if kind == "truthfulqa":
                    summary = _summarize_truthfulqa(path, data)
                    summary["responses"] = (data.get("responses") or [])[:50]
                    summary["raw_row_count"] = len(data.get("responses") or [])
                    return _attach_meta(summary)
                if kind == "consistency":
                    summary = _summarize_consistency(path, data)
                    summary["questions"] = (data.get("questions") or [])[:50]
                    summary["raw_row_count"] = len(data.get("questions") or [])
                    return _attach_meta(summary)
                if kind == "mmlu":
                    summary = _summarize_mmlu(path, data)
                    summary["per_subject"] = data.get("per_subject") or {}
                    summary["results"] = (data.get("results") or [])[:50]
                    summary["raw_row_count"] = len(data.get("results") or [])
                    return _attach_meta(summary)
                if kind == "tomi":
                    summary = _summarize_tomi(path, data)
                    summary["results"] = (data.get("results") or [])[:50]
                    summary["raw_row_count"] = len(data.get("results") or [])
                    return _attach_meta(summary)
    return None
