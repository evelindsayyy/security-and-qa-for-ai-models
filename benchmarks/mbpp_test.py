"""
MBPP (Mostly Basic Python Problems) Benchmark Testing Script

Tests an LLM's code generation ability by asking it to write Python functions,
then executing the generated code against the official unit tests.

Each problem has 3 unit tests. A problem is marked passed if all 3 pass.

USAGE:
    1. Set LITELLM_API_KEY in your .env file
    2. Run: python mbpp_test.py

ENV VARIABLES:
    LITELLM_API_KEY     - required
    LITELLM_BASE_URL    - default: https://litellm.oit.duke.edu/v1
    MBPP_MODEL          - default: openai/gpt-5.1-chat
    MBPP_OUTPUT         - default: results
    MBPP_SAMPLE         - number of problems to sample (default: 50, 0 = full dataset)
    MBPP_SEED           - random seed for sampling (default: 42)
    MBPP_TIMEOUT        - seconds before killing code execution (default: 5)
"""

import json
import os
import re
import subprocess
import sys
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

# ============================================================================
# CONFIGURATION
# ============================================================================

HERE = Path(__file__).resolve().parent
BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("DUKE_GATEWAY_KEY") or os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("MBPP_MODEL", "openai/gpt-5.1")
OUTPUT_DIR = os.getenv("MBPP_OUTPUT", str(HERE / "results"))
SAMPLE_SIZE = int(os.getenv("MBPP_SAMPLE", "50"))
SEED = int(os.getenv("MBPP_SEED", "42"))
TIMEOUT = int(os.getenv("MBPP_TIMEOUT", "5"))


# ============================================================================
# MODEL QUERYING
# ============================================================================

def query_model(problem: str, test_list: List[str]) -> str:
    """Ask the model to write a Python function for the given problem."""
    # Show the model the test cases so it knows the expected function signature
    tests_str = "\n".join(test_list)
    prompt = f"""Write a Python function to solve the following problem.
Return ONLY the function code, no explanation, no markdown, no imports unless necessary.

Problem: {problem}

Your function must pass these tests:
{tests_str}

Code:"""

    try:
        response = query_chat_completion(
            model=MODEL,
            base_url=BASE_URL,
            api_key=API_KEY,
            messages=[{"role": "user", "content": prompt}],
            temperature=1,
            max_tokens=1000,
        )
        return response_content(response)
    except Exception as e:
        print(f"  [ERROR] API error: {e}")
        return ""


# ============================================================================
# CODE EXTRACTION
# ============================================================================

def extract_code(raw: str) -> str:
    """
    Extract clean Python code from the model's response.
    Handles markdown code blocks and raw code.
    """
    # Strip markdown code fences
    fenced = re.search(r"```(?:python)?\s*\n(.*?)```", raw, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    return raw.strip()


# ============================================================================
# CODE EXECUTION
# ============================================================================

def run_tests(code: str, test_list: List[str], test_setup_code: str = "") -> Dict:
    """
    Execute the model's code against the unit tests in a subprocess.
    Returns a dict with passed count, total, and any error messages.
    """
    results = []

    for test in test_list:
        # Build a self-contained script: setup + model code + one test assertion
        script = "\n".join(filter(None, [
            test_setup_code,
            code,
            test,
        ]))

        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
            )
            passed = proc.returncode == 0
            error = proc.stderr.strip() if not passed else ""
        except subprocess.TimeoutExpired:
            passed = False
            error = f"Timed out after {TIMEOUT}s"
        except Exception as e:
            passed = False
            error = str(e)

        results.append({"test": test, "passed": passed, "error": error})

    passed_count = sum(1 for r in results if r["passed"])
    return {
        "passed": passed_count == len(test_list),  # all tests must pass
        "tests_passed": passed_count,
        "tests_total": len(test_list),
        "test_results": results,
    }


# ============================================================================
# MAIN TEST
# ============================================================================

def run_mbpp_test(dataset) -> Dict:
    """Run the full MBPP test and return results."""
    print(f"\n{'='*60}")
    print(f"Testing: {MODEL}")
    print(f"Problems: {len(dataset)}")
    print(f"{'='*60}")

    results = []
    correct = 0

    for idx, row in enumerate(dataset):
        task_id = row["task_id"]
        problem = row["text"]
        test_list = row["test_list"]
        test_setup_code = row.get("test_setup_code", "")

        raw_response = query_model(problem, test_list)
        code = extract_code(raw_response)

        if not code:
            print(f"  [FAIL] Q{idx+1} (task {task_id}): no code generated")
            results.append({
                "task_id": task_id,
                "problem": problem,
                "generated_code": "",
                "passed": False,
                "tests_passed": 0,
                "tests_total": len(test_list),
                "test_results": [],
            })
            continue

        exec_result = run_tests(code, test_list, test_setup_code)

        if exec_result["passed"]:
            correct += 1

        status = "OK" if exec_result["passed"] else "FAIL"
        print(f"  [{status}] Q{idx+1} (task {task_id}): "
              f"{exec_result['tests_passed']}/{exec_result['tests_total']} tests passed")

        # Print first error if any for quick debugging
        for t in exec_result["test_results"]:
            if not t["passed"] and t["error"]:
                print(f"         Error: {t['error'][:120]}")
                break

        results.append({
            "task_id": task_id,
            "problem": problem,
            "generated_code": code,
            "passed": exec_result["passed"],
            "tests_passed": exec_result["tests_passed"],
            "tests_total": exec_result["tests_total"],
            "test_results": exec_result["test_results"],
        })

    total = len(results)
    accuracy = round(correct / total, 4) if total > 0 else 0

    return {
        "model": MODEL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
        },
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
    path = out / f"mbpp_{model_slug}_{timestamp}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to {path}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY not set in environment")

    print("[OK] Loading MBPP dataset...")
    ds = load_dataset("google-research-datasets/mbpp", split="test")

    if SAMPLE_SIZE > 0:
        ds = ds.shuffle(seed=SEED).select(range(SAMPLE_SIZE))
        print(f"[OK] Sampled {SAMPLE_SIZE} problems (seed={SEED})")
    else:
        print(f"[OK] Using full dataset ({len(ds)} problems)")

    try:
        data = run_mbpp_test(ds)
        save_results(data, OUTPUT_DIR)

        s = data["summary"]
        bar_len = int(s["accuracy"] * 40)
        bar = "[" + "=" * bar_len + "-" * (40 - bar_len) + "]"
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"{MODEL:35s} {bar} {s['accuracy']:.1%} "
              f"({s['correct']}/{s['total']})")

    except Exception as e:
        print(f"[ERROR] {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()