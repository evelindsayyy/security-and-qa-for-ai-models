import json
import os
import re
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

from datasets import load_dataset
import litellm
import dotenv

from model_client import query_chat_completion, response_content

dotenv.load_dotenv()
litellm.suppress_debug_info = True

BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = (
    os.getenv("LITELLM_API_KEY")
    or os.getenv("DUKE_GATEWAY_KEY")
    or os.getenv("OPENAI_API_KEY")
)
MODEL = os.getenv("QUALITY_MODEL", "openai/gpt-5.1")
OUTPUT_DIR = os.getenv("QUALITY_OUTPUT", "test_results")
SAMPLE_SIZE = int(os.getenv("QUALITY_SAMPLE", "3"))   # number of articles
MAX_ROWS = int(os.getenv("QUALITY_MAX_ROWS", "0"))      # 0 = no limit
SEED = int(os.getenv("QUALITY_SEED", "42"))
HARD_ONLY = os.getenv("QUALITY_HARD_ONLY", "0") == "1"

LETTERS = ["A", "B", "C", "D"]


def parse_answer(text: str) -> str:
    """Extract a standalone A/B/C/D answer."""
    if not text:
        return ""

    text = text.strip().upper()

    match = re.search(r"\b([ABCD])\b", text)
    if match:
        return match.group(1)

    if text[0] in LETTERS:
        return text[0]

    return ""


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
            max_tokens=64,
        )

        content = response_content(response)
        return parse_answer(content)

    except Exception as e:
        print(f"  [ERROR] API error: {e}")
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
    total = 0

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
        passed = model_answer == correct_letter

        if passed:
            correct += 1
        total += 1

        status = "OK" if passed else "FAIL"
        hard_tag = " [HARD]" if difficult else ""

        print(
            f"    [{status}] Question {total}{hard_tag}: "
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
            "hard": difficult,
        })

    accuracy = round(correct / total, 4) if total else 0

    hard_results = [r for r in all_results if r["hard"]]
    hard_correct = sum(1 for r in hard_results if r["passed"])
    hard_accuracy = round(hard_correct / len(hard_results), 4) if hard_results else None

    return {
        "model": MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "hard_only": HARD_ONLY,
        "summary": {
            "total_questions": total,
            "correct": correct,
            "accuracy": accuracy,
            "hard_questions": len(hard_results),
            "hard_correct": hard_correct,
            "hard_accuracy": hard_accuracy,
        },
        "results": all_results,
    }


def save_results(data: Dict, output_dir: str):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = data["model"].replace(" ", "_").replace("/", "_")
    path = out / f"quality_{model_slug}_{timestamp}.json"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Results saved to {path}")


def print_summary(data: Dict):
    s = data["summary"]
    bar_len = int(s["accuracy"] * 40)
    bar = "[" + "=" * bar_len + "-" * (40 - bar_len) + "]"

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(
        f"{'Overall':40s} {bar} {s['accuracy']:.1%} "
        f"({s['correct']}/{s['total_questions']})"
    )

    if s["hard_accuracy"] is not None and not HARD_ONLY:
        hard_bar_len = int(s["hard_accuracy"] * 40)
        hard_bar = "[" + "=" * hard_bar_len + "-" * (40 - hard_bar_len) + "]"
        print(
            f"{'Hard questions only':40s} {hard_bar} {s['hard_accuracy']:.1%} "
            f"({s['hard_correct']}/{s['hard_questions']})"
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
        data = run_quality_test(ds)
        save_results(data, OUTPUT_DIR)
        print_summary(data)
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()