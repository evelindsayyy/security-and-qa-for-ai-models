"""
IFEval quick runner — single-file self-contained script.

Run: open the file in your editor and press Run (uses LITELLM_API_KEY env).
Outputs: auto-named JSONL files under results, e.g. ifeval_<model>_<timestamp>.jsonl.
"""

from datasets import load_dataset
import json
import os
import re
from dotenv import load_dotenv
import litellm
from tqdm import tqdm
from datetime import datetime, timezone
import sys
from pathlib import Path

from model_client import query_chat_completion, response_content
from benchmark_metrics import compute_coverage, coverage_warning, has_usable_text, slugify_model
from benchmark_run_stats import run_with_stats, write_stats_sidecar
from benchmark_progress import init_progress, tick

sys.path.insert(0, ".")  # so instructions_registry is importable
import instructions_registry

load_dotenv()

litellm.suppress_debug_info = True

BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("DUKE_GATEWAY_KEY") or os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("IFEVAL_MODEL", "openai/gpt-5.1")
HERE = Path(__file__).resolve().parent
# IFEVAL_OUTPUT is the output *directory* (matches run_benchmark.py and the
# other runners). IFEVAL_OUTPUT_FILE optionally pins a full file path.
OUTPUT_FILE = os.getenv("IFEVAL_OUTPUT_FILE")
OUTPUT_DIR = os.getenv("IFEVAL_OUTPUT", str(HERE / "results"))
SAMPLE_SIZE = int(os.getenv("IFEVAL_SAMPLE", "20"))
SEED = int(os.getenv("IFEVAL_SEED", "42"))

def safe_get_response(response):
    return response_content(response)

def judge(prompt, response_text, instruction_id_list, kwargs_list):
    """Use the official IFEval instruction-following judge."""
    violations = []
    per_instruction = []

    for instruction_id, kwargs in zip(instruction_id_list, kwargs_list):
        # Build the checker object for this instruction
        try:
            instruction_cls = instructions_registry.INSTRUCTION_DICT[instruction_id]
        except KeyError:
            # Unknown instruction — skip gracefully
            per_instruction.append({
                "instruction_id": instruction_id,
                "passed": None,
                "reason": "unknown_instruction_id",
            })
            continue

        instruction = instruction_cls(instruction_id)

        # kwargs may be a dict or None; the official API expects keyword args
        kw = kwargs if isinstance(kwargs, dict) else {}
        # Filter out None values — the checkers don't expect them
        kw = {k: v for k, v in kw.items() if v is not None}

        try:
            instruction.build_description(**kw)
            passed = instruction.check_following(response_text)
        except Exception as e:
            passed = False
            kw["_error"] = str(e)

        if not passed:
            violations.append(instruction_id)

        per_instruction.append({
            "instruction_id": instruction_id,
            "passed": passed,
            "kwargs": kw,
        })

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "per_instruction": per_instruction,
        "word_count": len(re.findall(r"\S+", (response_text or ""))),
    }


def save_jsonl(rows, path):
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def get_output_path(model: str) -> str:
    if OUTPUT_FILE:
        return OUTPUT_FILE

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = slugify_model(model)
    return os.path.join(OUTPUT_DIR, f"ifeval_{model_slug}_{timestamp}.jsonl")


def main():
    if not API_KEY:
        raise RuntimeError('LITELLM_API_KEY not set in environment')

    with run_with_stats():
        ds = load_dataset('google/IFEval', split='train')
        sample = ds.shuffle(seed=SEED).select(range(SAMPLE_SIZE)) if SAMPLE_SIZE > 0 else ds
        init_progress(
            total=len(sample),
            unit="prompts",
            message="Running IFEval…",
        )

        print(f"testing model {MODEL}")
        results = []
        for row in tqdm(sample, desc='IFEval'):
            try:
                response = query_chat_completion(
                    model=MODEL,
                    base_url=BASE_URL,
                    api_key=API_KEY,
                    messages=[{'role': 'user', 'content': row['prompt']}],
                    temperature=1,
                )
                text = safe_get_response(response)
            except Exception:
                text = ""
            judge_res = judge(row['prompt'], text, row.get('instruction_id_list', []), row.get('kwargs', []))

            results.append({
                'model': MODEL,
                'key': row.get('key'),
                'prompt': row['prompt'],
                'response': text,
                'answered': has_usable_text(text),
                'instruction_id_list': row.get('instruction_id_list', []),
                'kwargs': row.get('kwargs', []),
                'judge': judge_res,
                'ts': datetime.now(timezone.utc).isoformat()
            })
            tick(message=f"Prompt {len(results)}/{len(sample)}")

        output_path = get_output_path(MODEL)
        save_jsonl(results, output_path)
        write_stats_sidecar()

        attempted = len(results)
        scored = sum(1 for r in results if r['answered'])
        passed = sum(1 for r in results if r['answered'] and r['judge']['passed'])
        cov = compute_coverage(attempted=attempted, scored=scored)
        pass_rate = passed / scored if scored else 0

        print(f"Saved {len(results)} rows to {output_path}")
        print(f"Passed: {passed}/{scored} ({pass_rate * 100:.1f}%) over answered prompts")
        warn = coverage_warning(cov)
        if warn:
            print(warn.replace("accuracy is over answered items only",
                               "pass rate is over answered prompts only"))

        # Instruction-level accuracy (answered prompts only)
        all_instructions = [
            inst
            for r in results
            if r['answered']
            for inst in r['judge']['per_instruction']
            if inst.get('passed') is not None
        ]
        inst_passed = sum(1 for i in all_instructions if i['passed'])
        if all_instructions:
            print(f"Passed (instruction-level): {inst_passed}/{len(all_instructions)} "
                  f"({inst_passed/len(all_instructions)*100:.1f}%)")


if __name__ == '__main__':
    main()
