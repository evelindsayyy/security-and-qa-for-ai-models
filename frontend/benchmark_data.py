"""
Data source for /benchmarks and /benchmarks/<slug>.

Postgres when POSTGRES_DSN is set; artifact fallback otherwise.
Schema detection is content-based so renames do not break the viewer.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from frontend.path_safety import is_safe_slug, resolves_inside

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmarks.benchmark_metrics import coverage_extras  # noqa: E402
from benchmarks.benchmark_run_stats import load_stats_sidecar  # noqa: E402

COVERAGE_SKIP_EXPLANATION = (
    "Items marked SKIP had no usable model output — for example a blank response, "
    "an unparseable multiple-choice letter, failed code generation, an API or network "
    "error, a rate limit, or exhausted provider credits. Headline accuracy is computed "
    "over answered items only."
)

PRIMARY_DIR = ROOT / "benchmarks" / "results"
LEGACY_DIRS = (
    ROOT / "testing" / "basic_tests" / "test_results",
    ROOT / "test_results",
)

# Context shown on benchmark detail pages (about, field glossary, how to read scores).
BENCHMARK_META: dict[str, dict] = {
    "truthfulqa": {
        "title": "TruthfulQA",
        "headline_metric": "accuracy",
        "about": (
            "Multiple-choice factuality benchmark. Each question has several answer options; "
            "the model must pick the letter for the most truthful answer. Measures whether "
            "the model avoids common misconceptions and hedging traps."
        ),
        "procedure": (
            "A random sample of questions is drawn from the TruthfulQA MCQ set. Each item "
            "presents a question plus four answer options (A–D). The model is asked to choose "
            "the most truthful letter. The runner extracts the letter from the model's reply."
        ),
        "scoring": (
            "Headline accuracy is the fraction of answered questions where the model's "
            "letter matches the correct option. Items with no parseable letter are marked "
            "SKIP and excluded from the denominator. Random guessing would score ~25% per question."
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
        "headline_metric": "pass rate",
        "about": (
            "Instruction-following benchmark with verifiable constraints (e.g. \"no commas\", "
            "\"exactly N sentences\"). Each prompt lists instruction IDs; an automated judge "
            "checks whether the model's response satisfies every constraint."
        ),
        "procedure": (
            "A random sample of prompts is taken from the IFEval registry. Each prompt lists "
            "one or more formatting or content constraints by instruction ID. The model produces "
            "a free-form response; an automated judge checks every constraint individually."
        ),
        "scoring": (
            "Headline pass rate is the share of answered prompts where all constraints "
            "passed. A single failed constraint fails the whole prompt. Skipped prompts had no "
            "usable model output."
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
        "headline_metric": "mean F1",
        "about": (
            "Robustness check: the same underlying question is asked in several paraphrases. "
            "BERTScore F1 compares response pairs — high mean F1 means the model gives "
            "semantically similar answers regardless of wording."
        ),
        "procedure": (
            "Each topic in the pilot set has several paraphrases — same meaning, different "
            "wording. The model answers every paraphrase separately. BERTScore F1 is computed "
            "for each pair of responses within a topic, then averaged to a per-topic mean F1."
        ),
        "scoring": (
            "Headline mean F1 (0–1) is the average of per-topic mean F1 scores. This is "
            "not accuracy: lower scores can reflect different response length or structure, "
            "not necessarily contradictory conclusions. Open a run to see per-topic and pairwise "
            "breakdowns."
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
        "headline_metric": "accuracy",
        "about": (
            "Massive Multitask Language Understanding — multiple-choice questions across "
            "57 academic subjects. This pilot samples a subset by default (see runner env "
            "MMLU_SAMPLE). Overall accuracy is correct / total."
        ),
        "procedure": (
            "Questions are sampled at random from the MMLU test split across subjects such as "
            "history, law, STEM, and humanities. Each item is a four-option MCQ (A–D). The "
            "model sees the question and choices, then returns a letter."
        ),
        "scoring": (
            "Headline accuracy is correct answers divided by answered questions. "
            "Per-subject accuracy is available on the detail page. Blank or unparseable "
            "replies are SKIPped and do not count as wrong — they are excluded from the "
            "denominator."
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
        "headline_metric": "accuracy",
        "about": (
            "Theory-of-mind stories: characters move objects while others are absent. "
            "Questions test whether the model tracks beliefs vs. reality (first-order, "
            "second-order, memory, etc.)."
        ),
        "procedure": (
            "Each item is a short story followed by a question about what a character knows, "
            "remembers, or where an object is. The model returns a short free-form answer. "
            "Question types include memory, first-order belief, second-order belief, and reality."
        ),
        "scoring": (
            "Headline accuracy compares the model's answer to the expected short answer "
            "(exact match after normalization). Wrong answers count against accuracy; missing "
            "or empty replies are SKIPped."
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
    "mbpp": {
        "title": "MBPP (Mostly Basic Python Problems)",
        "headline_metric": "accuracy",
        "about": (
            "Code generation benchmark. Model writes Python; unit test checks run against generated code."
        ),
        "procedure": (
            "Each problem describes a Python task in plain language. The model generates code; "
            "the runner extracts a function and executes it against the problem's unit tests in a "
            "sandboxed subprocess (with a timeout)."
        ),
        "scoring": (
            "A problem passes only if all unit tests pass — there is no partial credit per "
            "problem. Headline accuracy is the fraction of answered problems that fully passed. "
            "Problems with no extractable code are SKIPped."
        ),
        "source": "https://github.com/google-research/google-research/tree/master/mbpp",
        "fields": [
            ("accuracy", "Fraction of problems where all unit tests passed."),
            ("tests_passed / tests_total", "Per-problem test pass count"),
            ("generated_code", "Extracted Python the model produced.")
        ],
        "item_label": "problem",
    },
    "quality": {
        "title": "QuALITY",
        "headline_metric": "accuracy",
        "about": (
            "Long-document reading comprehension. Model reads an article, then answers multiple-choice questions."
        ),
        "procedure": (
            "Each item pairs a long article with a multiple-choice question. The model receives "
            "the article and question with four options (A–D) and must pick the correct letter."
        ),
        "scoring": (
            "Headline accuracy is the fraction of answered questions where the model's letter "
            "matches the correct option. Some questions are marked hard on the detail page; "
            "hard-question accuracy is reported separately when present. Unparseable replies are "
            "SKIPped."
        ),
        "source": "https://github.com/nyu-mll/quality",
        "fields": [
            ("accuracy", "Fraction of MCQ questions answered correctly."),
            ("hard_accuracy", "Accuracy on questions marked as difficult (when present)."),
            ("model_answer", "Letter A-D the model chose."),
        ],
        "item_label": "question",
    },
}

# Per-benchmark orientation bands for reference scores (pilot sample sizes — not leaderboard claims).
SCORE_BANDS: dict[str, dict] = {
    "truthfulqa": {
        "mid": 0.55,
        "strong": 0.70,
        "hint": "Many models score 55-70% on this benchmark. Top models can score ~85%, while human experts can score ~94%.",
        "hint_sources": [
            {"label": "TruthfulQA paper", "url": "https://arxiv.org/abs/2109.07958"},
            {"label": "llm-stats.com", "url": "https://llm-stats.com/benchmarks/truthfulqa"},
        ],
    },
    "ifeval": {
        "mid": 0.80,
        "strong": 0.90,
        "hint": "Many models score 80-90% on this benchmark. Top models can score ~95%.",
        "hint_sources": [
            {"label": "llm-stats.com", "url": "https://llm-stats.com/benchmarks/ifeval"},
        ],
    },
    "mmlu": {
        "mid": 0.80,
        "strong": 0.90,
        "hint": "Many models score 80-90% on this benchmark. Top models can score ~95%, better than the human baseline of 90%.",
        "hint_sources": [
            {"label": "lmmarketcap.com", "url": "https://lmmarketcap.com/benchmarks/mmlu"},
        ],
    },
    "tomi": {
        "mid": 0.70,
        "strong": 0.85,
        "hint": "Older models score ~60% on this benchmark. Newer models might score better.",
        "hint_sources": [
            {"label": "Sap et al.", "url": "https://arxiv.org/abs/2210.13312"},
        ],
    },
    "consistency": {
        "mid": 0.75,
        "strong": 0.85,
        "hint": "Custom benchmark, measuring mean BERTScore F1 (0–1) between answers to paraphrased prompts. Many models score 80-85%. Lower scores often reflect different response length or structure, not necessarily contradictory conclusions.",
    },
    "mbpp": {
        "mid": 0.60,
        "strong": 0.80,
        "hint": "Many modern models score ~80% on this benchmark, with top models recording ~95%.",
        "hint_sources": [
            {"label": "Codesota", "url": "https://www.codesota.com/llm/humaneval-mbpp#mbpp"},
        ],
    },
    "quality": {
        "mid": 0.50,
        "strong": 0.70,
        "hint": "Many models struggle to reach 70% on this benchmark. Top models can score ~90%, while human experts score 93.5%.",
        "hint_sources": [
            {"label": "Official QuALITY leaderboard", "url": "https://nyu-mll.github.io/quality/"},
        ],
    },
}

REFERENCE_DIR = ROOT / "frontend" / "benchmark_refs"
_PREFERRED_REFERENCE_MODELS = ("GPT 4.1 Mini", "Llama 3.3")
_BENCHMARK_BADGE: dict[str, str] = {
    "truthfulqa": "badge-tqa",
    "ifeval": "badge-ifeval",
    "consistency": "badge-consistency",
    "mmlu": "badge-mmlu",
    "tomi": "badge-tomi",
    "mbpp": "badge-mbpp",
    "quality": "badge-quality",
}


def get_benchmark_guide_data() -> dict:
    """Rows for the shared 'How to read this' guide on list and reference pages."""
    from benchmarks.run_benchmark import BENCHMARKS  # noqa: E402

    rows: list[dict] = []
    for key, cfg in BENCHMARKS.items():
        meta = BENCHMARK_META.get(key, {})
        sample = cfg.get("sample") or {}
        rows.append({
            "key": key,
            "label": cfg["label"],
            "badge_class": _BENCHMARK_BADGE.get(key, "badge-pilot"),
            "title": meta.get("title", cfg["label"]),
            "about": meta.get("about", ""),
            "procedure": meta.get("procedure", ""),
            "scoring": meta.get("scoring", ""),
            "headline_metric": meta.get("headline_metric", ""),
            "source": meta.get("source", ""),
            "default_sample": sample.get("default"),
            "sample_label": sample.get("label", "Items"),
            "sample_unit": sample.get("unit", "items"),
        })
    return {
        "guide_rows": rows,
        "coverage_skip_explanation": COVERAGE_SKIP_EXPLANATION,
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
            **coverage_extras(metrics),
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
        "n": summary.get("scored") or summary.get("total") or len(data.get("results") or []),
        "extras": {
            "subjects": len(data.get("per_subject") or {}),
            **coverage_extras(summary),
        },
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
        "n": summary.get("scored") or summary.get("total") or len(data.get("results") or []),
        "extras": coverage_extras(summary),
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
        "n": summary.get("scored") or summary.get("total_questions") or len(data.get("questions") or []),
        "extras": coverage_extras(summary),
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
    has_answered = any("answered" in r for r in rows)
    if has_answered:
        answered_rows = [r for r in rows if r.get("answered")]
        attempted = len(rows)
        scored = len(answered_rows)
        passed = sum(1 for r in answered_rows if (r.get("judge") or {}).get("passed"))
    else:
        attempted = scored = len(rows)
        passed = sum(1 for r in rows if (r.get("judge") or {}).get("passed"))
    rate = passed / scored if scored else None
    model = rows[0].get("model") or "—"
    ts_raw = rows[0].get("ts") or ""
    summary = {
        "attempted": attempted,
        "scored": scored,
        "failed": max(0, attempted - scored),
        "coverage": round(scored / attempted, 4) if attempted else 0.0,
    }
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
        "n": scored,
        "extras": {"passed": passed, "total": scored, **coverage_extras(summary)},
    }
    
def _summarize_mbpp(path: Path, data: dict) -> dict:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "mbpp",
        "kind_label": "MBPP",
        "model": data.get("model") or "—",
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "headline_metric": "accuracy",
        "headline_value": acc,
        "headline_display": f"{acc:.1%}" if acc is not None else "—",
        "n": summary.get("scored") or summary.get("total") or len(data.get("results") or []),
        "extras": {
            "correct": summary.get("correct"),
            **coverage_extras(summary),
        },
    }


def _normalize_model_name(raw: str) -> str:
    if not raw or raw == "—":
        return raw
    if "/" in raw:
        return raw.rsplit("/", 1)[-1]
    return raw


def _score_class(kind: str, value: float | None) -> str:
    if value is None:
        return ""
    bands = SCORE_BANDS.get(kind) or {"mid": 0.6, "strong": 0.8}
    if value >= bands["strong"]:
        return "score-strong"
    if value >= bands["mid"]:
        return "score-mid"
    return "score-weak"


def _reference_dir() -> Path | None:
    return REFERENCE_DIR if REFERENCE_DIR.is_dir() else None


def _coverage_info(row: dict) -> dict:
    """Normalize partial-run coverage for list/detail/reference views."""
    extras = row.get("extras") or {}
    failed = int(extras.get("failed") or 0)
    attempted = extras.get("attempted")
    scored = extras.get("scored")
    n = row.get("n")
    if failed <= 0:
        return {
            "partial": False,
            "failed": 0,
            "n_display": str(n if n is not None else "—"),
        }
    if attempted is not None and scored is not None:
        n_display = f"{scored}/{attempted}"
    else:
        n_display = str(n if n is not None else "—")
    return {
        "partial": True,
        "failed": failed,
        "attempted": attempted,
        "scored": scored,
        "coverage_pct": extras.get("coverage"),
        "n_display": n_display,
    }


def _attach_coverage(summary: dict) -> dict:
    cov = _coverage_info(summary)
    summary["coverage"] = cov
    summary["n_display"] = cov["n_display"]
    summary["coverage_skip_explanation"] = COVERAGE_SKIP_EXPLANATION
    return summary


def is_reference_slug(slug: str) -> bool:
    ref = _reference_dir()
    if ref is None or not is_safe_slug(slug):
        return False
    for suffix in (".json", ".jsonl"):
        path = ref / f"{slug}{suffix}"
        if path.is_file() and resolves_inside(ref, path):
            return True
    return False


def _load_reference_summaries() -> list[dict]:
    ref = _reference_dir()
    if ref is None:
        return []
    rows: list[dict] = []
    for path in sorted(list(ref.glob("*.json")) + list(ref.glob("*.jsonl"))):
        row = _summarize_file(path)
        if row is None:
            continue
        row = dict(row)
        row["model"] = _normalize_model_name(row.get("model") or "—")
        row["is_reference"] = True
        row["score_class"] = _score_class(row.get("kind"), row.get("headline_value"))
        rows.append(row)
    return rows


def _reference_by_kind_model() -> dict[str, dict[str, dict]]:
    """Index of committed reference runs keyed by benchmark kind and model name."""
    by_kind_model: dict[str, dict[str, dict]] = {}
    for row in _load_reference_summaries():
        kind = row.get("kind")
        model = row.get("model")
        if kind and model and model != "—":
            by_kind_model.setdefault(kind, {})[model] = row
    return by_kind_model


def _format_reference_delta(kind: str, delta: float) -> str:
    if kind == "consistency":
        return f"{delta:+.3f}"
    return f"{delta * 100:+.1f} pp"


def _reference_comparison_entry(
    kind: str,
    your_value: float,
    ref: dict,
    *,
    exact_match: bool,
) -> dict | None:
    ref_value = ref.get("headline_value")
    if ref_value is None:
        return None
    delta = your_value - ref_value
    if delta > 1e-9:
        delta_class = "ref-delta-up"
    elif delta < -1e-9:
        delta_class = "ref-delta-down"
    else:
        delta_class = "ref-delta-flat"
    return {
        "model": ref.get("model"),
        "exact_match": exact_match,
        "slug": ref["slug"],
        "headline_metric": ref.get("headline_metric"),
        "headline_display": ref["headline_display"],
        "headline_value": ref_value,
        "n_display": _coverage_info(ref)["n_display"],
        "delta_value": delta,
        "delta_display": _format_reference_delta(kind, delta),
        "delta_class": delta_class,
    }


def _attach_reference_comparison(summary: dict) -> dict:
    """Attach delta vs reference baseline(s) for user runs."""
    if summary.get("is_reference"):
        return summary
    kind = summary.get("kind")
    model = _normalize_model_name(summary.get("model") or "—")
    your_value = summary.get("headline_value")
    if not kind or model == "—" or your_value is None:
        return summary
    by_kind = _reference_by_kind_model().get(kind, {})
    if not by_kind:
        return summary

    if model in by_kind:
        ref_targets = [(by_kind[model], True)]
    else:
        available = set(by_kind)
        ordered = [m for m in _PREFERRED_REFERENCE_MODELS if m in available]
        ordered.extend(sorted(available - set(ordered)))
        ref_targets = [(by_kind[m], False) for m in ordered]

    entries: list[dict] = []
    for ref, exact_match in ref_targets:
        entry = _reference_comparison_entry(
            kind, your_value, ref, exact_match=exact_match,
        )
        if entry:
            entries.append(entry)
    if entries:
        summary["reference_comparisons"] = entries
    return summary


def _build_reference_section() -> dict:
    from benchmarks.run_benchmark import BENCHMARKS  # noqa: E402

    summaries = _load_reference_summaries()
    if not summaries:
        return {"has_reference": False, "reference_models": [], "reference_rows": []}

    by_kind_model: dict[str, dict[str, dict]] = {}
    for row in summaries:
        kind = row.get("kind")
        model = row.get("model")
        if not kind or not model or model == "—":
            continue
        by_kind_model.setdefault(kind, {})[model] = row

    models_set = {m for per in by_kind_model.values() for m in per}
    reference_models = [m for m in _PREFERRED_REFERENCE_MODELS if m in models_set]
    reference_models.extend(sorted(models_set - set(reference_models)))

    reference_rows: list[dict] = []
    for key, cfg in BENCHMARKS.items():
        cells: dict[str, dict] = {}
        for model in reference_models:
            cell = by_kind_model.get(key, {}).get(model)
            if cell:
                cells[model] = {
                    "slug": cell["slug"],
                    "headline_display": cell["headline_display"],
                    "headline_metric": cell["headline_metric"],
                    "headline_value": cell["headline_value"],
                    "n": cell["n"],
                    "score_class": cell["score_class"],
                    "coverage": _coverage_info(cell),
                }
        reference_rows.append({
            "key": key,
            "label": cfg["label"],
            "cells": cells,
        })

    return {
        "has_reference": True,
        "reference_models": reference_models,
        "reference_rows": reference_rows,
        "coverage_skip_explanation": COVERAGE_SKIP_EXPLANATION,
    }


def _summarize_quality(path: Path, data: dict) -> dict:
    summary = data.get("summary") or {}
    acc = summary.get("accuracy")
    return {
        "slug": path.stem,
        "filename": path.name,
        "kind": "quality",
        "kind_label": "QuALITY",
        "model": data.get("model") or "—",
        "timestamp_raw": data.get("timestamp") or "",
        "timestamp": _format_ts(data.get("timestamp") or ""),
        "headline_metric": "accuracy",
        "headline_value": acc,
        "headline_display": f"{acc:.1%}" if acc is not None else "—",
        "n": summary.get("scored") or summary.get("total_questions") or len(data.get("results") or []),
        "extras": {
            "hard_accuracy": summary.get("hard_accuracy"),
            "hard_questions": summary.get("hard_questions"),
            **coverage_extras(summary),
        },
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
    if kind == "mbpp":
        return _summarize_mbpp(path, data)
    if kind == "quality":
        return _summarize_quality(path, data)
    return None


def _run_stats_chips(rs: dict) -> list[dict[str, str]]:
    chips: list[dict[str, str]] = []
    wall = rs.get("wall_time_sec")
    if wall is not None:
        chips.append({"label": "runtime", "value": f"{wall:.1f}s"})
    lat = rs.get("latency_ms") or {}
    if lat.get("mean") is not None:
        chips.append({"label": "latency", "value": f"{lat['mean']:.0f} ms mean"})
    tokens = rs.get("tokens") or {}
    total = tokens.get("total")
    if total is not None:
        chips.append({"label": "tokens", "value": f"{int(total):,} total"})
    calls = rs.get("api_calls")
    if calls:
        failed = int(rs.get("api_calls_failed") or 0)
        if failed:
            chips.append({"label": "API calls", "value": f"{calls} ({failed} failed)"})
        else:
            chips.append({"label": "API calls", "value": str(calls)})
    return chips


def _extract_run_stats(data: dict | None, path: Path) -> dict:
    if data:
        for key in ("summary", "metrics"):
            block = data.get(key)
            if isinstance(block, dict):
                rs = block.get("run_stats")
                if isinstance(rs, dict):
                    return rs
    return load_stats_sidecar(path)


def _attach_run_stats(summary: dict, path: Path, data: dict | None = None) -> dict:
    rs = _extract_run_stats(data, path)
    if rs:
        summary["run_stats_chips"] = _run_stats_chips(rs)
    return summary


def _attach_meta(summary: dict) -> dict:
    """Add benchmark context block for the detail template."""
    kind = summary.get("kind")
    meta = dict(BENCHMARK_META.get(kind, {}))
    summary["meta"] = meta
    return summary


def _result_dirs() -> list[Path]:
    dirs = list(_candidate_dirs())
    ref = _reference_dir()
    if ref is not None:
        dirs.append(ref)
    return dirs


def _dedupe_key(row: dict) -> tuple[str, str] | None:
    kind = row.get("kind")
    model = _normalize_model_name(row.get("model") or "—")
    if not kind or model == "—":
        return None
    return (model, kind)


def _postprocess_benchmark_runs(runs: list[dict]) -> dict:
    """Keep the latest run per (model, benchmark); sort best score first."""
    all_runs = list(runs)
    latest: dict[tuple[str, str], dict] = {}
    for r in sorted(
        all_runs,
        key=lambda row: (row.get("timestamp_raw") or "", row.get("filename") or ""),
    ):
        key = _dedupe_key(r)
        if key is not None:
            latest[key] = r

    key_counts: dict[tuple[str, str], int] = {}
    for r in all_runs:
        key = _dedupe_key(r)
        if key is not None:
            key_counts[key] = key_counts.get(key, 0) + 1

    for r in all_runs:
        key = _dedupe_key(r)
        if key is None:
            r["is_latest"] = True
            r["older_run_count"] = 0
        else:
            r["is_latest"] = latest.get(key) is r
            r["older_run_count"] = max(key_counts.get(key, 1) - 1, 0)

    deduped = list(latest.values())
    deduped.sort(
        key=lambda r: (
            r.get("headline_value") if r.get("headline_value") is not None else -1.0,
            r.get("timestamp_raw") or "",
        ),
        reverse=True,
    )
    all_runs.sort(key=lambda r: r.get("timestamp_raw") or "", reverse=True)

    kinds = sorted({r["kind_label"] for r in deduped})
    models = sorted({
        r["model"] for r in deduped
        if r.get("model") and not str(r["model"]).startswith("—")
    })
    return {
        "runs": deduped,
        "all_runs": all_runs,
        "run_count": len(deduped),
        "all_run_count": len(all_runs),
        "kinds": kinds,
        "models": models,
    }


def _get_benchmarks_data_files() -> dict:
    from frontend.read_context import artifact_path_visible

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
            if not artifact_path_visible(d / path.stem, pillar="benchmark"):
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


def _get_benchmark_detail_files(slug: str) -> dict | None:
    from frontend.read_context import artifact_path_visible

    if not is_safe_slug(slug):
        return None
    ref = _reference_dir()
    for d in _result_dirs():
        # Reference runs are canonical baselines, not user-owned — always visible.
        if d != ref and not artifact_path_visible(d / slug, pillar="benchmark"):
            continue
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
                    _attach_run_stats(summary, path)
                    return _attach_meta(summary)
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if kind == "truthfulqa":
                    summary = _summarize_truthfulqa(path, data)
                    summary["responses"] = (data.get("responses") or [])[:50]
                    summary["raw_row_count"] = len(data.get("responses") or [])
                    _attach_run_stats(summary, path, data)
                    return _attach_meta(summary)
                if kind == "consistency":
                    summary = _summarize_consistency(path, data)
                    summary["questions"] = (data.get("questions") or [])[:50]
                    summary["raw_row_count"] = len(data.get("questions") or [])
                    _attach_run_stats(summary, path, data)
                    return _attach_meta(summary)
                if kind == "mmlu":
                    summary = _summarize_mmlu(path, data)
                    summary["per_subject"] = data.get("per_subject") or {}
                    summary["results"] = (data.get("results") or [])[:50]
                    summary["raw_row_count"] = len(data.get("results") or [])
                    _attach_run_stats(summary, path, data)
                    return _attach_meta(summary)
                if kind == "tomi":
                    summary = _summarize_tomi(path, data)
                    summary["results"] = (data.get("results") or [])[:50]
                    summary["raw_row_count"] = len(data.get("results") or [])
                    _attach_run_stats(summary, path, data)
                    return _attach_meta(summary)
                if kind == "mbpp":
                    summary = _summarize_mbpp(path, data)
                    summary["results"] = (data.get("results") or [])[:50]
                    summary["raw_row_count"] = len(data.get("results") or [])
                    _attach_run_stats(summary, path, data)
                    return _attach_meta(summary)
                if kind == "quality":
                    summary = _summarize_quality(path, data)
                    summary["results"] = (data.get("results") or [])[:50]
                    summary["raw_row_count"] = len(data.get("results") or [])
                    _attach_run_stats(summary, path, data)
                    return _attach_meta(summary)
    return None


# Artifact suffixes for a benchmark run stem (under benchmarks/results/ or legacy dirs).
_ARTIFACT_SUFFIXES = (".json", ".jsonl", ".stats.json", ".progress.json", ".log")


def _artifact_paths(slug: str) -> list[Path]:
    """All on-disk files for *slug* under known results directories."""
    if not is_safe_slug(slug):
        return []
    found: list[Path] = []
    for base in _candidate_dirs():
        for suffix in _ARTIFACT_SUFFIXES:
            path = base / f"{slug}{suffix}"
            if path.is_file() and resolves_inside(base, path):
                found.append(path)
    return found


def delete_benchmark(slug: str) -> str | None:
    """Remove benchmark artifacts (and DB row when configured).

    Returns an error message, or None on success.
    """
    if not is_safe_slug(slug):
        return f"invalid slug: {slug!r}"

    if is_reference_slug(slug):
        return "reference benchmark runs cannot be deleted"

    from frontend.benchmark_launch import is_run_in_progress

    if is_run_in_progress(slug):
        return "cannot delete while the run is still in progress"

    removed_files = 0
    for path in _artifact_paths(slug):
        try:
            path.unlink()
            removed_files += 1
        except OSError as exc:
            return f"could not delete {path.name}: {exc}"

    removed_db = False
    try:
        from frontend import benchmark_db_data

        if benchmark_db_data.available():
            removed_db = benchmark_db_data.delete_run(slug)
    except Exception:
        pass

    if removed_files == 0 and not removed_db:
        return f"no benchmark result found for slug {slug!r}"
    return None


# Public entry points — Postgres when configured, artifact fallback otherwise.


def get_benchmark_reference_data() -> dict:
    data = _build_reference_section()
    data.update(get_benchmark_guide_data())
    return data


def get_benchmarks_data() -> dict:
    try:
        from frontend import benchmark_db_data

        if benchmark_db_data.available():
            data = benchmark_db_data.get_benchmarks_data_db()
        else:
            data = _get_benchmarks_data_files()
    except Exception:
        data = _get_benchmarks_data_files()
    ref = _build_reference_section()
    data["has_reference"] = ref.get("has_reference", False)
    data["coverage_skip_explanation"] = COVERAGE_SKIP_EXPLANATION
    raw_runs = data.pop("runs", [])
    data.update(_postprocess_benchmark_runs(raw_runs))
    for row in data.get("all_runs", []):
        row["score_class"] = _score_class(row.get("kind"), row.get("headline_value"))
        row["coverage"] = _coverage_info(row)
    return data


def get_benchmark_detail(slug: str) -> dict | None:
    detail: dict | None = None
    if is_reference_slug(slug):
        detail = _get_benchmark_detail_files(slug)
        if detail is not None:
            detail["is_reference"] = True
            detail["model"] = _normalize_model_name(detail.get("model") or "—")
    else:
        try:
            from frontend import benchmark_db_data

            if benchmark_db_data.available():
                detail = benchmark_db_data.get_benchmark_detail_db(slug)
        except Exception:
            pass
        if detail is None:
            detail = _get_benchmark_detail_files(slug)
    if detail is not None:
        detail["score_class"] = _score_class(detail.get("kind"), detail.get("headline_value"))
        _attach_coverage(detail)
        _attach_reference_comparison(detail)
    return detail
