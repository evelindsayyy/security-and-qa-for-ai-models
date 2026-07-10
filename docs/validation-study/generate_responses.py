"""
Generate the A/B model responses for the judge-validation survey.

Fills responses.jsonl with one row per (prompt, model):
    {"source": "<suite:id>", "model": "<display label>", "text": "<response>"}
which build_versions.py reads to fill the surveys + Forms paste sheets.

Models (every comparison is DPO target vs an opponent -> on-policy for the DPO run):
  * Qwen2.5-7B-Instruct  — the DPO target, served on the DCC (a5000, vLLM).
      Reached via an OpenAI-compatible endpoint (default http://localhost:8000/v1,
      override with $QWEN_ENDPOINT). Its API model id is the served HF id.
  * GPT 4.1 Mini, GPT 4.1 Nano — opponents, plain gateway calls (no serving).

Run from the REPO ROOT (so .env / the gateway key load):
    uv run python docs/validation-study/generate_responses.py --set gateway   # now
    uv run python docs/validation-study/generate_responses.py --set qwen      # once Qwen is up
    uv run python docs/validation-study/generate_responses.py --set all

Idempotent: existing (source, model) rows are skipped, and generate_candidate has
its own cache, so re-runs are free. Failures are not written (they retry next run).
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "evaluator"))

from candidate import generate_candidate  # noqa: E402

RESP_PATH = HERE / "responses.jsonl"
POOL_PATH = HERE / "item_pool.jsonl"
SYSTEM_PROMPT = "You are a helpful assistant. Answer the user's request directly."
TEMPERATURE = 0.2
MAX_TOKENS = 800   # chat models answer well within this; the GPT-5 reasoning
                   # family (dropped) needed far more, which is why we avoid it

# (display label, api model id, endpoint)  — endpoint None = Duke gateway
QWEN_ENDPOINT = os.environ.get("QWEN_ENDPOINT", "http://localhost:8000/v1")
MODELS = {
    "gateway": [
        ("GPT 4.1 Mini", "GPT 4.1 Mini", None),
        ("GPT 4.1 Nano", "GPT 4.1 Nano", None),
    ],
    "qwen": [
        ("Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-7B-Instruct", QWEN_ENDPOINT),
    ],
}


def unique_prompts() -> list[tuple[str, str]]:
    """(source, prompt) once each — a model answers a prompt once, not per item."""
    seen: dict[str, str] = {}
    for line in POOL_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            o = json.loads(line)
            seen.setdefault(o["source"], o["prompt"])
    return list(seen.items())


def already_done(path: Path) -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["source"], r["model"]))
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["gateway", "qwen", "all"], default="gateway")
    ap.add_argument("--only", default=None, help="restrict to one model display label")
    ap.add_argument("--out", default=None, help="output jsonl name (default responses.jsonl)")
    args = ap.parse_args()

    out_path = (HERE / args.out) if args.out else RESP_PATH
    models = (MODELS["gateway"] + MODELS["qwen"]) if args.set == "all" else MODELS[args.set]
    if args.only:
        models = [m for m in models if m[0] == args.only]
    prompts = unique_prompts()
    done = already_done(out_path)
    todo = [(s, p, lbl, api, ep) for (s, p) in prompts
            for (lbl, api, ep) in models if (s, lbl) not in done]

    print(f"{len(prompts)} prompts x {len(models)} model(s); {len(todo)} to generate "
          f"({len(done)} already done)")
    ok = fail = 0
    with out_path.open("a", encoding="utf-8") as out:
        for i, (source, prompt, label, api, ep) in enumerate(todo, 1):
            r = generate_candidate(model=api, system_prompt=SYSTEM_PROMPT, question=prompt,
                                   temperature=TEMPERATURE, max_tokens=MAX_TOKENS, endpoint=ep)
            failed = getattr(r, "failed", False) or not (r.response or "").strip()
            tag = "via DCC" if ep else "gateway"
            if failed:
                fail += 1
                print(f"[{i}/{len(todo)}] {label:22s} {source:34s} FAIL "
                      f"({getattr(r, 'error', 'empty') or 'empty'})")
                continue
            out.write(json.dumps({"source": source, "model": label,
                                  "text": r.response.strip()}, ensure_ascii=False) + "\n")
            out.flush()
            ok += 1
            print(f"[{i}/{len(todo)}] {label:22s} {source:34s} ok ({tag}, "
                  f"{len(r.response)} chars)")
    print(f"\ndone: {ok} written, {fail} failed. -> {out_path.name}")
    if fail:
        print("re-run the same command to retry failures (successes are cached/ skipped).")


if __name__ == "__main__":
    main()
