"""
ToMi Theory of Mind Benchmark Testing Script

Can LLMs reason about others' beliefs, even if they are false?

Tests an LLM on the ToMi benchmark, which evaluates theory of mind reasoning.
Each story involves characters moving objects between locations, followed by
questions about the characters' beliefs and the object's location.

Question types:
  - memory:    Where was the object at the beginning?
  - reality:   Where is the object now?
  - first_order:  Where does character A think the object is?
  - second_order: Where does A think B thinks the object is?

USAGE:
    1. Place tomi_questions.txt in the same folder as this script
    2. Set LITELLM_API_KEY in your .env file
    3. Run: python tomi_test.py
"""

import json
import os
import re
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from litellm import completion
import litellm
import dotenv

dotenv.load_dotenv()

litellm.suppress_debug_info = True

# ============================================================================
# CONFIGURATION
# ============================================================================

BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("DUKE_GATEWAY_KEY") or os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("TOMI_MODEL", "openai/gpt-5.4")
HERE = Path(__file__).resolve().parent
OUTPUT_DIR = os.getenv("TOMI_OUTPUT", str(HERE / "results"))
TOMI_FILE = os.getenv("TOMI_FILE", "tomi_questions.txt")
SAMPLE_LIMIT = int(os.getenv("TOMI_LIMIT", "10"))  # 0 = no limit


# ============================================================================
# PARSING
# ============================================================================

def classify_question(question: str) -> str:
    """Classify a question into one of the four ToMi question types."""
    q = question.lower()
    if "think that" in q or "searches for" in q:
        return "second_order"
    elif "will" in q and "look for" in q:
        return "first_order"
    elif "where does" in q or "where will" in q:
        return "first_order"
    elif "beginning" in q or "at the start" in q:
        return "memory"
    else:
        return "reality"


def parse_tomi_file(path: str) -> List[Dict]:
    """
    Parse the tomi_questions.txt file into a list of story+question dicts.
    Blocks are detected by the next line number resetting to 1, so stories
    can have variable length.
    """
    stories = []
    with open(path, 'r', encoding='utf-8') as f:
        lines = [line.rstrip('\n') for line in f if line.strip()]

    blocks = []
    current_block: List[str] = []
    for line in lines:
        if re.match(r'^\s*1\s+', line) and current_block:
            blocks.append(current_block)
            current_block = []
        current_block.append(line)

    if current_block:
        blocks.append(current_block)

    story_id = 0
    for block in blocks:
        if len(block) < 2:
            continue

        story_lines = []
        for line in block[:-1]:
            match = re.match(r'^\s*\d+\s+(.+)$', line)
            story_lines.append(match.group(1).strip() if match else line.strip())

        q_line = block[-1]
        q_line = re.sub(r'^\s*\d+\s+', '', q_line).strip()
        parts = q_line.split('\t')
        if len(parts) < 2:
            parts = re.split(r'\s{2,}', q_line)

        if len(parts) < 2:
            continue

        question_text = parts[0].strip().rstrip('?').strip() + '?'
        correct_answer = parts[1].strip()
        question_type = classify_question(question_text)

        stories.append({
            'id': story_id,
            'story': ' '.join(story_lines),
            'story_lines': story_lines,
            'question': question_text,
            'correct_answer': correct_answer,
            'question_type': question_type,
        })
        story_id += 1

    return stories


# ============================================================================
# MODEL QUERYING
# ============================================================================

def query_model(story: str, question: str) -> str:
    """Query the model with a ToMi story and question."""
    prompt = f"""Read the following story carefully, then answer the question.

Story:
{story}

Question: {question}

Answer with ONLY the location (one word). Do not explain."""

    try:
        response = completion(
            model=MODEL,
            api_base=BASE_URL,
            api_key=API_KEY,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=1000,
        )
        return response.choices[0].message.content.strip().lower() or ""
    except Exception as e:
        print(f"  [ERROR] API error: {e}")
        return ""


# ============================================================================
# EVALUATION
# ============================================================================

def normalize_answer(answer: str) -> str:
    """Normalize answer for comparison — lowercase, strip punctuation."""
    return re.sub(r'[^\w\s]', '', answer.lower()).strip()


def check_answer(model_answer: str, correct_answer: str) -> bool:
    """Check if the model's answer matches the correct answer."""
    return normalize_answer(model_answer) == normalize_answer(correct_answer)


def run_tomi_test(stories: List[Dict]) -> Dict:
    """Run the full ToMi test and return results."""
    print(f"\n{'='*60}")
    print(f"Testing: {MODEL}")
    print(f"Stories: {len(stories)}")
    print(f"{'='*60}")

    results = []
    correct = 0

    for idx, item in enumerate(stories):
        model_answer = query_model(item['story'], item['question'])
        passed = check_answer(model_answer, item['correct_answer'])
        if passed:
            correct += 1

        status = "OK" if passed else "FAIL"
        print(f"  [{status}] Q{idx+1} ({item['question_type']}): "
              f"expected={item['correct_answer']} got={model_answer}")

        results.append({
            'id': item['id'],
            'question_type': item['question_type'],
            'story': item['story'],
            'question': item['question'],
            'correct_answer': item['correct_answer'],
            'model_answer': model_answer,
            'passed': passed,
        })

    total = len(results)
    accuracy = correct / total if total > 0 else 0

    return {
        'model': MODEL,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'total': total,
            'correct': correct,
            'accuracy': round(accuracy, 4),
        },
        'results': results,
    }


# ============================================================================
# SAVING
# ============================================================================

def save_results(data: Dict, output_dir: str):
    """Save results to a JSON file."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = data['model'].replace(' ', '_').replace('/', '_')
    path = out / f"tomi_{model_slug}_{timestamp}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to {path}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY not set in environment")

    print(f"[OK] Loading ToMi data from {TOMI_FILE}")
    stories = parse_tomi_file(TOMI_FILE)
    print(f"[OK] Parsed {len(stories)} stories")

    if SAMPLE_LIMIT > 0:
        stories = stories[:SAMPLE_LIMIT]
        print(f"[OK] Limited to {SAMPLE_LIMIT} stories")

    try:
        data = run_tomi_test(stories)
        save_results(data, OUTPUT_DIR)

        s = data['summary']
        bar_len = int(s['accuracy'] * 40)
        bar = '[' + '=' * bar_len + '-' * (40 - bar_len) + ']'
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"{MODEL:35s} {bar} {s['accuracy']:.1%} "
              f"({s['correct']}/{s['total']})")

    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()


if __name__ == '__main__':
    main()