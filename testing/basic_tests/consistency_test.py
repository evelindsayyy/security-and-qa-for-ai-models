"""
LLM Consistency Testing Script

Tests whether a model gives semantically consistent answers when the same
question is asked in different ways. Uses BERTScore to compare responses.

USAGE:
    1. Create a consistency_questions.json file (see format below)
    2. Edit the MODEL CONFIGURATION section
    3. Run: python consistency_test.py

QUESTIONS FILE FORMAT (consistency_questions.json):
[
    {
        "id": "q1",
        "topic": "AI safety",
        "paraphrases": [
            "Should AI systems be regulated by governments?",
            "Do you think government regulation of AI is a good idea?",
            "Is it important for governments to oversee artificial intelligence development?"
        ]
    },
    ...
]

EXPLANATION FOR USERS:

This test measures whether a model gives the same answer regardless of how a question is phrased. Each question is asked in 3 different ways — same meaning, different wording — and the model's responses are compared to see how similar they are.
Similarity is measured using BERTScore, which compares the meaning of responses rather than just the exact words used. Two responses that say the same thing in different ways will still score highly.
The result is a score from 0 to 1 for each question, and an overall average across all questions. A score closer to 1 means the model answered consistently regardless of phrasing. A lower score means the model's answers varied depending on how the question was worded, which could indicate sensitivity to phrasing or unstable reasoning.
What this tells you: A model that scores well here is more predictable and reliable — users are likely to get the same quality of answer regardless of how they phrase their prompt. A model that scores poorly might give very different answers to essentially the same question, which can be a sign of inconsistent reasoning.

SCORING:

Above 0.90 - very consistent, essentially saying the same thing
0.85-0.90 - mostly consistent, minor differences in emphasis
0.75-0.85 - noticeable inconsistency, different angles on the topic
Below 0.75 - significantly inconsistent responses
"""

import json
import os
import itertools
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional
from litellm import completion
import litellm
from bert_score import score as bert_score
import dotenv

dotenv.load_dotenv()

litellm.suppress_debug_info = True

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = os.getenv("LITELLM_BASE_URL", "https://litellm.oit.duke.edu/v1")
API_KEY = os.getenv("LITELLM_API_KEY")
MODEL = os.getenv("CONSISTENCY_MODEL", "openai/Llama 3.3")
OUTPUT_DIR = os.getenv("CONSISTENCY_OUTPUT", "test_results")
QUESTIONS_FILE = os.getenv("CONSISTENCY_QUESTIONS", "consistency_questions.json")
QUESTION_LIMIT = int(os.getenv("CONSISTENCY_LIMIT", "5")) # 0 means no limit

# BERTScore language model to use for scoring
# "en" is fine for English; can also use a specific model name
BERTSCORE_MODEL = "distilbert-base-uncased"


# ============================================================================
# HELPERS
# ============================================================================

def load_questions(path: str) -> List[Dict]:
    with open(path, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    print(f"[OK] Loaded {len(questions)} questions from {path}")
    return questions


def query_model(model: str, prompt: str) -> str:
    """Send a single prompt to the model and return the response text."""
    try:
        response = completion(
            model=model,
            api_base=BASE_URL,
            api_key=API_KEY,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"  [ERROR] API error: {e}")
        return ""


def compute_pairwise_bertscore(responses: List[str]) -> Dict:
    """
    Compute BERTScore for all pairs of responses.
    Returns mean F1, min F1, and per-pair scores.
    """
    if len(responses) < 2:
        return {"mean_f1": None, "min_f1": None, "pairs": []}

    pairs = list(itertools.combinations(range(len(responses)), 2))
    candidates = [responses[i] for i, j in pairs]
    references = [responses[j] for i, j in pairs]

    _, _, f1 = bert_score(
        candidates,
        references,
        model_type=BERTSCORE_MODEL,
        verbose=False,
    )
    f1_scores = f1.tolist()

    pair_results = [
        {
            "response_a": i,
            "response_b": j,
            "f1": round(f1_scores[idx], 4),
        }
        for idx, (i, j) in enumerate(pairs)
    ]

    return {
        "mean_f1": round(sum(f1_scores) / len(f1_scores), 4),
        "min_f1": round(min(f1_scores), 4),
        "pairs": pair_results,
    }


def run_consistency_test(model_name: str, questions: List[Dict]) -> Dict:
    """Run the full consistency test for one model."""
    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"{'='*60}")

    question_results = []

    for q in questions:
        q_id = q.get("id", "?")
        topic = q.get("topic", "")
        paraphrases = q["paraphrases"]

        print(f"\n  Question [{q_id}]: {topic}")
        responses = []

        for idx, prompt in enumerate(paraphrases):
            print(f"    Paraphrase {idx+1}: {prompt[:80]}...")
            response = query_model(model_name, prompt)
            print(f"    Response:    {response[:80]}...")
            responses.append(response)

        # Filter out empty responses before scoring
        valid = [(p, r) for p, r in zip(paraphrases, responses) if r.strip()]
        if len(valid) < 2:
            print(f"  [WARN] Not enough valid responses for question {q_id}, skipping.")
            continue

        valid_paraphrases, valid_responses = zip(*valid)
        scores = compute_pairwise_bertscore(list(valid_responses))

        print(f"    BERTScore mean F1: {scores['mean_f1']} | "
              f"min F1: {scores['min_f1']} | ")

        question_results.append({
            "id": q_id,
            "topic": topic,
            "paraphrases": list(valid_paraphrases),
            "responses": list(valid_responses),
            "bertscore": scores,
        })

    # Aggregate
    scored = [r for r in question_results if r["bertscore"]["mean_f1"] is not None]
    mean_f1_overall = (
        round(sum(r["bertscore"]["mean_f1"] for r in scored) / len(scored), 4)
        if scored else None
    )

    return {
        "model": model_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_questions": len(question_results),
            "mean_f1_overall": mean_f1_overall,
        },
        "questions": question_results,
    }


def save_results(results: Dict, output_dir: str):
    """Save results to a JSON file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = results["model"].replace(" ", "_").replace("/", "_")
    path = out / f"{model_slug}_consistency_{timestamp}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to {path}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY not set in environment")

    questions = load_questions(QUESTIONS_FILE)
    if QUESTION_LIMIT > 0:
        questions = questions[:QUESTION_LIMIT]
    
    summary_rows = []
    try:
        results = run_consistency_test(
            model_name=MODEL,
            questions=questions,
        )
        save_results(results, OUTPUT_DIR)
        summary_rows.append((MODEL, results["summary"]))
    except Exception as e:
        print(f"[ERROR] Failed testing {MODEL}: {e}")
        traceback.print_exc()

    # Print summary table
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, s in summary_rows:
        print(f"{name:35s} mean F1: {s['mean_f1_overall']} ({s['total_questions']} questions)")


if __name__ == "__main__":
    main()