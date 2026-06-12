"""
IFEval quick runner — single-file self-contained script.

Run: open the file in your editor and press Run (uses LITELLM_API_KEY env).
Outputs: auto-named JSONL files under test_results, e.g. ifeval_<model>_<timestamp>.jsonl.
"""

from datasets import load_dataset
import json
import os
import re
from dotenv import load_dotenv
from litellm import completion
from tqdm import tqdm
from datetime import datetime, timezone
import sys
from pathlib import Path
sys.path.insert(0, ".")  # so instructions_registry is importable
import instructions_registry

load_dotenv()

BASE_URL = os.getenv("LITELLM_BASE_URL") or os.getenv("DUKE_GATEWAY_URL") or "https://litellm.oit.duke.edu/v1"
API_KEY = os.getenv("LITELLM_API_KEY") or os.getenv("DUKE_GATEWAY_KEY") or os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("IFEVAL_MODEL", "openai/gpt-5.4")
OUTPUT_FILE = os.getenv("IFEVAL_OUTPUT")
HERE = Path(__file__).resolve().parent
OUTPUT_DIR = os.getenv("IFEVAL_OUTPUT_DIR", str(HERE / "results"))
SAMPLE_SIZE = int(os.getenv("IFEVAL_SAMPLE", "10"))
SEED = int(os.getenv("IFEVAL_SEED", "42"))

def safe_get_response(response):
    if response is None:
        return ""
    try:
        # litellm-style object
        if hasattr(response, 'choices') and response.choices:
            first = response.choices[0]
            if hasattr(first, 'message'):
                return getattr(first.message, 'content', '') or ''
            return getattr(first, 'text', '') or ''

        # dict-like fallback
        if isinstance(response, dict):
            choices = response.get('choices')
            if isinstance(choices, list) and choices:
                c = choices[0]
                if isinstance(c, dict):
                    msg = c.get('message')
                    if isinstance(msg, dict):
                        return msg.get('content', '') or ''
                    return c.get('text', '') or ''
            return str(response)
    except Exception:
        return str(response)

    return str(response)

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
    model_slug = model.replace(" ", "_").replace("/", "_")
    return os.path.join(OUTPUT_DIR, f"ifeval_{model_slug}_{timestamp}.jsonl")


def main():
    if not API_KEY:
        raise RuntimeError('LITELLM_API_KEY not set in environment')

    ds = load_dataset('google/IFEval', split='train')
    sample = ds.shuffle(seed=SEED).select(range(SAMPLE_SIZE)) if SAMPLE_SIZE > 0 else ds

    print(f"testing model {MODEL}")
    results = []
    for row in tqdm(sample, desc='IFEval'):
        response = completion(
            model=MODEL,
            api_base=BASE_URL,
            api_key=API_KEY,
            messages=[{'role':'user','content': row['prompt'] }],
            temperature=1,
        )
        text = safe_get_response(response)
        judge_res = judge(row['prompt'], text, row.get('instruction_id_list', []), row.get('kwargs', []))

        results.append({
            'model': MODEL,
            'key': row.get('key'),
            'prompt': row['prompt'],
            'response': text,
            'instruction_id_list': row.get('instruction_id_list', []),
            'kwargs': row.get('kwargs', []),
            'judge': judge_res,
            'ts': datetime.now(timezone.utc).isoformat()
        })

    output_path = get_output_path(MODEL)
    save_jsonl(results, output_path)

    passed = sum(1 for r in results if r['judge']['passed'])
    total = len(results)
    print(f"Saved {len(results)} rows to {output_path}")
    print(f"Passed: {passed}/{total} ({(passed/total*100) if total else 0:.1f}%)")
    
    # Instruction-level accuracy
    all_instructions = [
        inst
        for r in results
        for inst in r['judge']['per_instruction']
        if inst.get('passed') is not None
    ]
    inst_passed = sum(1 for i in all_instructions if i['passed'])
    if all_instructions:
        print(f"Passed (instruction-level): {inst_passed}/{len(all_instructions)} "
              f"({inst_passed/len(all_instructions)*100:.1f}%)")


if __name__ == '__main__':
    main()
