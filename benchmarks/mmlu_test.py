"""
MMLU (Massive Multitask Language Understanding) Benchmark Testing Script

Tests an LLM across 57 academic subjects using multiple-choice questions.
Reports overall accuracy and per-subject breakdown.

USAGE:
    1. Set LITELLM_API_KEY in your .env file
    2. Run: python mmlu_test.py

ENV VARIABLES:
    LITELLM_API_KEY     - required
    LITELLM_BASE_URL    - default: https://litellm.oit.duke.edu/v1
    MMLU_MODEL          - default: openai/gpt-5.1
    MMLU_OUTPUT         - default: results
    MMLU_SAMPLE         - number of questions to sample (default: 100, 0 = full dataset)
    MMLU_SEED           - random seed for sampling (default: 42)
"""

import json
import os
import traceback
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List
from datasets import load_dataset
import litellm
import dotenv

from model_client import query_chat_completion, response_content, extract_choice_letter

dotenv.load_dotenv()

litellm.suppress_debug_info = True

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("DUKE_GATEWAY_KEY") or os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("MMLU_MODEL", "openai/gpt-5.1")
HERE = Path(__file__).resolve().parent
OUTPUT_DIR = os.getenv("MMLU_OUTPUT", str(HERE / "results"))
SAMPLE_SIZE = int(os.getenv("MMLU_SAMPLE", "100"))
SEED = int(os.getenv("MMLU_SEED", "42"))

LETTERS = ["A", "B", "C", "D"]


# ============================================================================
# HELPERS
# ============================================================================

def format_prompt(question: str, choices: List[str]) -> str:
    """Format a multiple choice question as a prompt."""
    prompt = (
        "Answer the following multiple-choice question. "
        "Respond with ONLY the letter (A, B, C, or D).\n\n"
        f"Question: {question}\n\n"
    )
    for letter, choice in zip(LETTERS, choices):
        prompt += f"{letter}. {choice}\n"
    prompt += "\nYour answer (A/B/C/D):"
    return prompt


def query_model(question: str, choices: List[str]) -> str:
    """Send a question to the model and return the chosen letter."""
    prompt = format_prompt(question, choices)
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
        return extract_choice_letter(content, "".join(LETTERS))
    except Exception as e:
        print(f"  [ERROR] API error: {e}")
        return ""


# ============================================================================
# MAIN TEST
# ============================================================================

def run_mmlu_test(dataset) -> Dict:
    """Run the MMLU test and return full results."""
    print(f"\n{'='*60}")
    print(f"Testing: {MODEL}")
    print(f"Questions: {len(dataset)}")
    print(f"{'='*60}")

    results = []
    subject_stats = defaultdict(lambda: {"correct": 0, "total": 0})

    for idx, row in enumerate(dataset):
        question = row["question"]
        choices = row["choices"]
        correct_idx = row["answer"]
        correct_letter = LETTERS[correct_idx]
        subject = row["subject"]

        model_answer = query_model(question, choices)
        passed = model_answer == correct_letter

        subject_stats[subject]["total"] += 1
        if passed:
            subject_stats[subject]["correct"] += 1

        status = "OK" if passed else "FAIL"
        print(f"  [{status}] Q{idx+1} ({subject}): "
              f"expected={correct_letter} got={model_answer or '?'}")

        results.append({
            "subject": subject,
            "question": question,
            "choices": choices,
            "correct_answer": correct_letter,
            "model_answer": model_answer,
            "passed": passed,
        })

    # Compute per-subject accuracy
    per_subject = {
        subject: {
            "correct": stats["correct"],
            "total": stats["total"],
            "accuracy": round(stats["correct"] / stats["total"], 4) if stats["total"] > 0 else 0,
        }
        for subject, stats in sorted(subject_stats.items())
    }

    total = len(results)
    correct = sum(1 for r in results if r["passed"])
    accuracy = round(correct / total, 4) if total > 0 else 0

    return {
        "model": MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
        },
        "per_subject": per_subject,
        "results": results,
    }


# ============================================================================
# SAVING
# ============================================================================

def save_results(data: Dict, output_dir: str):
    """Save results to a JSON file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = data["model"].replace(" ", "_").replace("/", "_")
    path = out / f"mmlu_{model_slug}_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to {path}")


def print_summary(data: Dict):
    """Print overall and per-subject accuracy to terminal."""
    s = data["summary"]
    bar_len = int(s["accuracy"] * 40)
    bar = "[" + "=" * bar_len + "-" * (40 - bar_len) + "]"

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Overall':40s} {bar} {s['accuracy']:.1%} ({s['correct']}/{s['total']})")

    print(f"\n{'='*70}")
    print("PER-SUBJECT BREAKDOWN")
    print(f"{'='*70}")
    for subject, stats in data["per_subject"].items():
        bar_len = int(stats["accuracy"] * 40)
        bar = "[" + "=" * bar_len + "-" * (40 - bar_len) + "]"
        print(f"  {subject:38s} {bar} {stats['accuracy']:.1%} "
              f"({stats['correct']}/{stats['total']})")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY not set in environment")

    print("[OK] Loading MMLU dataset...")
    ds = load_dataset("cais/mmlu", "all", split="test")

    if SAMPLE_SIZE > 0:
        ds = ds.shuffle(seed=SEED).select(range(SAMPLE_SIZE))
        print(f"[OK] Sampled {SAMPLE_SIZE} questions (seed={SEED})")
    else:
        print(f"[OK] Using full dataset ({len(ds)} questions)")

    try:
        data = run_mmlu_test(ds)
        save_results(data, OUTPUT_DIR)
        print_summary(data)
    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()