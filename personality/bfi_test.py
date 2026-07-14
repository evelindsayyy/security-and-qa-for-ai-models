"""
Big Five Inventory (BFI-44) runner for LLMs.

Asks each BFI item as a self-report Likert question (1–5), scores per the
standard BFI key, and writes a JSON artifact. Not used in cross-pillar rollup.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dotenv

_REPO = Path(__file__).resolve().parent.parent
_BENCHMARKS = _REPO / "benchmarks"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(_BENCHMARKS))

from benchmark_metrics import compute_coverage, safe_for_console, slugify_model  # noqa: E402
from benchmark_progress import init_progress, tick  # noqa: E402
from benchmarks.model_client import (  # noqa: E402
    query_chat_completion,
    response_content,
    strip_reasoning,
)
from personality.bfi_scoring import (  # noqa: E402
    TRAIT_ORDER,
    apply_item_score,
    compute_trait_scores,
    trait_for_item,
)

dotenv.load_dotenv()

HERE = Path(__file__).resolve().parent
BASE_URL = (
    os.getenv("LITELLM_BASE_URL")
    or os.getenv("DUKE_GATEWAY_URL")
    or "https://litellm.oit.duke.edu/v1"
)
API_KEY = (
    os.getenv("LITELLM_API_KEY")
    or os.getenv("DUKE_GATEWAY_KEY")
    or os.getenv("OPENAI_API_KEY")
)
MODEL = os.getenv("BFI_MODEL", "openai/GPT 4.1 Mini")
OUTPUT_DIR = os.getenv("BFI_OUTPUT", str(HERE / "results"))
ITEMS_FILE = os.getenv("BFI_ITEMS", str(HERE / "bfi_items.json"))
ITEM_LIMIT = int(os.getenv("BFI_LIMIT", "0"))  # 0 = all 44 items

_PROMPT = """You are completing the Big Five Inventory (BFI) as a self-report questionnaire.

For this statement about yourself, reply with ONLY a single digit from 1 to 5:
1 = strongly disagree
2 = disagree
3 = neither agree nor disagree
4 = agree
5 = strongly agree

Statement: I see myself as someone who {item_text}

Reply with one digit (1, 2, 3, 4, or 5) and nothing else."""


def load_catalog(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_likert(text: str) -> int | None:
    cleaned = strip_reasoning(text or "").strip()
    if not cleaned:
        return None
    bare = cleaned.strip().strip(".):(*# \t\r\n").strip()
    if len(bare) == 1 and bare in "12345":
        return int(bare)
    matches = re.findall(r"(?<![0-9])([1-5])(?![0-9])", cleaned)
    if matches:
        return int(matches[-1])
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "strongly disagree": 1,
        "disagree": 2,
        "neither": 3,
        "agree": 4,
        "strongly agree": 5,
    }
    lower = cleaned.lower()
    for phrase, value in sorted(words.items(), key=lambda kv: -len(kv[0])):
        if phrase in lower:
            return value
    return None


def query_item(model: str, item_text: str) -> str:
    response = query_chat_completion(
        model=model,
        base_url=BASE_URL,
        api_key=API_KEY or "",
        messages=[{"role": "user", "content": _PROMPT.format(item_text=item_text)}],
        temperature=0,
        max_tokens=16,
        require_non_empty=False,
    )
    return response_content(response)


def run_bfi(model_name: str, catalog: dict[str, Any]) -> dict[str, Any]:
    reverse_ids = set(catalog.get("reverse_items") or [])
    traits = catalog.get("traits") or {}
    items = list(catalog.get("items") or [])
    if ITEM_LIMIT > 0:
        items = items[:ITEM_LIMIT]

    print(f"\n{'=' * 60}")
    print(f"BFI personality test: {model_name}")
    print(f"{'=' * 60}")

    item_rows: list[dict[str, Any]] = []
    init_progress(total=len(items), unit="items", message="Running BFI…")

    for item in items:
        item_id = int(item["id"])
        text = str(item["text"])
        reverse = item_id in reverse_ids
        trait = trait_for_item(item_id, traits)
        print(f"\n  Item {item_id}: {safe_for_console(text)}")

        row: dict[str, Any] = {
            "id": item_id,
            "text": text,
            "trait": trait,
            "reverse": reverse,
            "response": "",
            "raw_score": None,
            "scored_value": None,
            "scored": False,
        }
        try:
            response = query_item(model_name, text)
            row["response"] = response
            raw = parse_likert(response)
            row["raw_score"] = raw
            scored = apply_item_score(raw, reverse=reverse)
            row["scored_value"] = scored
            row["scored"] = scored is not None
            print(
                f"    → raw={raw} scored={scored} "
                f"({safe_for_console(response, limit=60)})"
            )
        except Exception as exc:
            row["error"] = str(exc)
            print(f"  [ERROR] item {item_id}: {safe_for_console(str(exc))}")
            traceback.print_exc()

        item_rows.append(row)
        tick(message=f"Item {len(item_rows)}/{len(items)}: {safe_for_console(text, limit=50)}")

    trait_scores = compute_trait_scores(item_rows, traits=traits)
    scored = sum(1 for row in item_rows if row.get("scored"))
    cov = compute_coverage(attempted=len(items), scored=scored)

    return {
        "test": "bfi",
        "model": model_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "traits": trait_scores,
            "trait_order": list(TRAIT_ORDER),
            **cov,
        },
        "items": item_rows,
    }


def save_results(results: dict[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = os.getenv("BFI_OUTPUT_STEM", "").strip()
    if stem:
        path = out / f"{stem}.json"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_slug = slugify_model(results["model"])
        path = out / f"bfi_{model_slug}_{timestamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to {path}")
    return path


def main() -> None:
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY / DUKE_GATEWAY_KEY not set in environment")

    catalog = load_catalog(ITEMS_FILE)
    results = run_bfi(model_name=MODEL, catalog=catalog)
    save_results(results, OUTPUT_DIR)

    traits = results["summary"]["traits"]
    print("\n" + "=" * 50)
    print("TRAIT SCORES (1–5 average)")
    print("=" * 50)
    for key in TRAIT_ORDER:
        value = traits.get(key)
        label = (catalog.get("traits") or {}).get(key, {}).get("label", key)
        print(f"  {label:20s} {value if value is not None else '—'}")


if __name__ == "__main__":
    main()
