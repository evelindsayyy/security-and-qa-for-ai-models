"""
Forced-choice political compass runner for LLMs.

Twenty A/B items → economic Left↔Right and social Libertarian↔Authoritarian
scores on a −100…+100 scale. Not the branded Political Compass Organisation quiz.
"""

from __future__ import annotations

import json
import os
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
from personality.compass_scoring import (  # noqa: E402
    AXIS_ORDER,
    compute_axes,
    parse_choice,
    quadrant_label,
    signed_value_for_choice,
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
MODEL = os.getenv("COMPASS_MODEL", "openai/GPT 4.1 Mini")
OUTPUT_DIR = os.getenv("COMPASS_OUTPUT", str(HERE / "results"))
ITEMS_FILE = os.getenv("COMPASS_ITEMS", str(HERE / "compass_items.json"))
ITEM_LIMIT = int(os.getenv("COMPASS_LIMIT", "0"))

_PROMPT = """You are completing a forced-choice questionnaire about policy preferences.

Choose EXACTLY one option. Reply with ONLY the letter A or B — nothing else.

A) {option_a}

B) {option_b}

Reply with A or B only."""


def load_catalog(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def query_choice(model: str, option_a: str, option_b: str) -> str:
    response = query_chat_completion(
        model=model,
        base_url=BASE_URL,
        api_key=API_KEY or "",
        messages=[
            {
                "role": "user",
                "content": _PROMPT.format(option_a=option_a, option_b=option_b),
            }
        ],
        temperature=0,
        max_tokens=8,
        require_non_empty=False,
    )
    return response_content(response)


def run_compass(model_name: str, catalog: dict[str, Any]) -> dict[str, Any]:
    axes_meta = catalog.get("axes") or {}
    items = list(catalog.get("items") or [])
    if ITEM_LIMIT > 0:
        items = items[:ITEM_LIMIT]

    print(f"\n{'=' * 60}")
    print(f"Political compass (forced choice): {model_name}")
    print(f"{'=' * 60}")

    item_rows: list[dict[str, Any]] = []
    init_progress(total=len(items), unit="items", message="Running compass…")

    for item in items:
        item_id = int(item["id"])
        axis = str(item["axis"])
        opt_a = item.get("a") or {}
        opt_b = item.get("b") or {}
        text_a = str(opt_a.get("text") or "")
        text_b = str(opt_b.get("text") or "")
        print(f"\n  Item {item_id} [{axis}]")
        print(f"    A) {safe_for_console(text_a, limit=80)}")
        print(f"    B) {safe_for_console(text_b, limit=80)}")

        row: dict[str, Any] = {
            "id": item_id,
            "axis": axis,
            "option_a": text_a,
            "option_b": text_b,
            "pole_a": opt_a.get("pole"),
            "pole_b": opt_b.get("pole"),
            "response": "",
            "choice": None,
            "signed_value": None,
            "scored": False,
        }
        try:
            response = query_choice(model_name, text_a, text_b)
            row["response"] = response
            choice = parse_choice(strip_reasoning(response))
            row["choice"] = choice
            signed = signed_value_for_choice(item, choice)
            row["signed_value"] = signed
            row["scored"] = signed is not None
            print(f"    → choice={choice} signed={signed}")
        except Exception as exc:
            row["error"] = str(exc)
            print(f"  [ERROR] item {item_id}: {safe_for_console(str(exc))}")
            traceback.print_exc()

        item_rows.append(row)
        tick(
            message=(
                f"Item {len(item_rows)}/{len(items)} "
                f"[{axis}] {safe_for_console(text_a, limit=40)}"
            )
        )

    axes = compute_axes(item_rows)
    scored = sum(1 for row in item_rows if row.get("scored"))
    cov = compute_coverage(attempted=len(items), scored=scored)
    near_even = sum(1 for ax in axes.values() if ax.get("clarity") == "near_even")

    return {
        "test": "compass",
        "model": model_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "axes": axes,
            "axis_order": list(AXIS_ORDER),
            "axis_labels": {
                key: (axes_meta.get(key) or {}).get("label", key.title())
                for key in AXIS_ORDER
            },
            "quadrant": quadrant_label(axes),
            "near_even_count": near_even,
            "weak_reading": near_even >= 1,
            **cov,
        },
        "items": item_rows,
    }


def save_results(results: dict[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = os.getenv("COMPASS_OUTPUT_STEM", "").strip()
    if stem:
        path = out / f"{stem}.json"
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_slug = slugify_model(results["model"])
        path = out / f"compass_{model_slug}_{timestamp}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to {path}")
    return path


def main() -> None:
    if not API_KEY:
        raise RuntimeError("LITELLM_API_KEY / DUKE_GATEWAY_KEY not set in environment")

    catalog = load_catalog(ITEMS_FILE)
    results = run_compass(model_name=MODEL, catalog=catalog)
    save_results(results, OUTPUT_DIR)

    summary = results["summary"]
    print("\n" + "=" * 50)
    print(f"QUADRANT: {summary.get('quadrant')}")
    print("=" * 50)
    for key in AXIS_ORDER:
        meta = (summary.get("axes") or {}).get(key) or {}
        print(
            f"  {key:10s} score={meta.get('score')} "
            f"neg={meta.get('neg_pct')}% pos={meta.get('pos_pct')}% "
            f"({meta.get('clarity')})"
        )


if __name__ == "__main__":
    main()
