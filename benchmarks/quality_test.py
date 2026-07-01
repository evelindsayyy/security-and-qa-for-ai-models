import json
import os
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

from datasets import load_dataset
import litellm
import dotenv

from model_client import query_chat_completion, response_content, extract_choice_letter
from benchmark_metrics import (
    accuracy_bar,
    compute_coverage,
    has_usable_text,
    print_binary_summary,
    slugify_model,
    summarize_binary_accuracy,
)
from benchmark_run_stats import attach_run_stats, run_with_stats, write_stats_sidecar
from benchmark_progress import init_progress, tick

dotenv.load_dotenv()
litellm.suppress_debug_info = True

BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = (
    os.getenv("LITELLM_API_KEY")
    or os.getenv("DUKE_GATEWAY_KEY")
    or os.getenv("OPENAI_API_KEY")
)
HERE = Path(__file__).resolve().parent
MODEL = os.getenv("QUALITY_MODEL", "openai/gpt-5.1")
OUTPUT_DIR = os.getenv("QUALITY_OUTPUT", str(HERE / "results"))
SAMPLE_SIZE = int(os.getenv("QUALITY_SAMPLE", "3"))   # number of articles
MAX_ROWS = int(os.getenv("QUALITY_MAX_ROWS", "0"))      # 0 = no limit
SEED = int(os.getenv("QUALITY_SEED", "42"))
HARD_ONLY = os.getenv("QUALITY_HARD_ONLY", "0") == "1"

LETTERS = ["A", "B", "C", "D"]


def parse_answer(text: str) -> str:
    """Extract a standalone A/B/C/D answer (shared, model-agnostic extractor)."""
    return extract_choice_letter(text, "".join(LETTERS))


def query_model(article: str, question: str, options: List[str]) -> str:
    options_str = "\n".join(
        f"{letter}. {opt}" for letter, opt in zip(LETTERS, options)
    )

    prompt = (
        "Read the following passage carefully, then answer the multiple-choice question.\n\n"
        f"Passage:\n{article}\n\n"
        f"Question: {question}\n\n"
        f"{options_str}\n\n"
        "Respond with ONLY the letter A, B, C, or D.\n"
        "Your answer:"
    )

    try:
        response = query_chat_completion(
            model=MODEL,
            base_url=BASE_URL,
            api_key=API_KEY,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=1000,
        )

        content = response_content(response)
        return parse_answer(content)

    except Exception:
        return ""


def sample_articles(ds):
    """Sample whole articles, not individual rows/questions."""
    if SAMPLE_SIZE <= 0:
        return ds

    unique_article_ids = sorted(set(ds["article_id"]))
    sample_n = min(SAMPLE_SIZE, len(unique_article_ids))

    sampled_ids = (
        ds.shuffle(seed=SEED)
        .unique("article_id")[:sample_n]
    )

    return ds.filter(lambda row: row["article_id"] in set(sampled_ids))


def run_quality_test(dataset) -> Dict:
    print(f"\n{'=' * 60}")
    print(f"Testing: {MODEL}")
    print(f"Rows/questions: {len(dataset)}")
    print(f"Unique articles: {len(set(dataset['article_id']))}")
    print(f"Hard only: {HARD_ONLY}")
    print(f"{'=' * 60}")

    all_results = []
    correct = 0
    scored = 0
    init_progress(total=len(dataset), unit="questions", message="Running QuALITY…")

    for row_num, row in enumerate(dataset, start=1):
        if MAX_ROWS > 0 and row_num > MAX_ROWS:
            break

        article = row["article"]
        question = row["question"]
        options = row["options"]
        gold = row["gold_label"]
        difficult = bool(row.get("difficult", 0))

        if HARD_ONLY and not difficult:
            continue

        correct_letter = LETTERS[int(gold) - 1]

        print(
            f"\n  Row {row_num} | Article {row['article_id']} "
            f"({len(article.split())} words)"
        )

        model_answer = query_model(article, question, options)
        answered = has_usable_text(model_answer)
        passed = answered and model_answer == correct_letter

        if answered:
            scored += 1
        if passed:
            correct += 1

        status = "OK" if passed else ("SKIP" if not answered else "FAIL")
        hard_tag = " [HARD]" if difficult else ""

        print(
            f"    [{status}] Question {len(all_results) + 1}{hard_tag}: "
            f"expected={correct_letter} got={model_answer or '?'}"
        )

        all_results.append({
            "row_num": row_num,
            "article_id": row["article_id"],
            "question_unique_id": row["question_unique_id"],
            "title": row.get("title", ""),
            "question": question,
            "options": options,
            "correct_answer": correct_letter,
            "model_answer": model_answer,
            "passed": passed,
            "answered": answered,
            "hard": difficult,
        })
        tick(message=f"Question {len(all_results)}/{len(dataset)}")

    attempted = len(all_results)
    summary = summarize_binary_accuracy(attempted=attempted, correct=correct, scored=scored)
    # Keep quality-specific field names for downstream readers.
    summary["total_questions"] = summary["scored"]
    summary["total_evaluated"] = summary["scored"]

    hard_results = [r for r in all_results if r["hard"]]
    hard_scored = [r for r in hard_results if r["answered"]]
    hard_correct = sum(1 for r in hard_scored if r["passed"])
    summary["hard_questions"] = len(hard_results)
    summary["hard_scored"] = len(hard_scored)
    summary["hard_correct"] = hard_correct
    summary["hard_accuracy"] = (
        round(hard_correct / len(hard_scored), 4) if hard_scored else None
    )
    if hard_results:
        hard_cov = compute_coverage(attempted=len(hard_results), scored=len(hard_scored))
        summary["hard_attempted"] = hard_cov["attempted"]
        summary["hard_failed"] = hard_cov["failed"]
        summary["hard_coverage"] = hard_cov["coverage"]

    return {
        "model": MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hard_only": HARD_ONLY,
        "summary": summary,
        "results": all_results,
    }


def save_results(data: Dict, output_dir: str):
    attach_run_stats(data["summary"])
    write_stats_sidecar()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = slugify_model(data["model"])
    path = out / f"quality_{model_slug}_{timestamp}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Results saved to {path}")


def print_summary(data: Dict):
    s = data["summary"]
    print_binary_summary("Overall", s)

    if s.get("hard_accuracy") is not None and not HARD_ONLY:
        hard_bar = accuracy_bar(s["hard_accuracy"])
        print(
            f"{'Hard questions only':40s} {hard_bar} {s['hard_accuracy']:.1%} "
            f"({s['hard_correct']}/{s.get('hard_scored', s['hard_questions'])})"
        )
        if s.get("hard_failed"):
            print(
                f"  [WARN] hard subset: {s.get('hard_scored', 0)}/{s.get('hard_attempted', 0)} "
                f"answered ({s.get('hard_coverage', 0):.0%} coverage)"
            )


def main():
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY not set in environment")

    print("[OK] Loading QuALITY dataset...")
    ds = load_dataset("tasksource/QuALITY", split="validation")

    ds = sample_articles(ds)

    if SAMPLE_SIZE > 0:
        print(
            f"[OK] Sampled {SAMPLE_SIZE} articles "
            f"({len(ds)} question rows, seed={SEED})"
        )
    else:
        print(
            f"[OK] Using full dataset "
            f"({len(ds)} question rows, {len(set(ds['article_id']))} articles)"
        )

    try:
        with run_with_stats():
            data = run_quality_test(ds)
            save_results(data, OUTPUT_DIR)
            print_summary(data)
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()