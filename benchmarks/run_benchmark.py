#!/usr/bin/env python3
"""
Unified entrypoint for public benchmark runners (browser + Docker + CLI).

Wraps the individual *_test.py scripts Jack authored under benchmarks/.
Sets model/output env vars, runs the script, then copies the newest output to a
stable stem so the frontend can poll ``results/<stem>.{json,jsonl}``.

Usage:
    python run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"
    python run_benchmark.py --benchmark ifeval --model "gpt-5-chat" --output-stem my-run
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"


def _safe_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model.strip())[:80] or "model"


BENCHMARKS: dict[str, dict] = {
    "truthfulqa": {
        "label": "TruthfulQA MCQ",
        "script": "tqa_test.py",
        "glob": "tqa_*.json",
        "env_model": "TQA_MODEL",
        "env_output": "TQA_OUTPUT_DIR",
    },
    "ifeval": {
        "label": "IFEval",
        "script": "if_test.py",
        "glob": "ifeval_*.jsonl",
        "env_model": "IFEVAL_MODEL",
        "env_output": "IFEVAL_OUTPUT_DIR",
    },
    "mmlu": {
        "label": "MMLU (Massive Multitask Language Understanding)",
        "script": "mmlu_test.py",
        "glob": "mmlu_*.json",
        "env_model": "MMLU_MODEL",
        "env_output": "MMLU_OUTPUT",
    },
    "tomi": {
        "label": "ToMi (Theory of Mind)",
        "script": "tomi_test.py",
        "glob": "tomi_*.json",
        "env_model": "TOMI_MODEL",
        "env_output": "TOMI_OUTPUT",
    },
    "consistency": {
        "label": "Consistency",
        "script": "consistency_test.py",
        "glob": "consistency_*.json",
        "env_model": "CONSISTENCY_MODEL",
        "env_output": "CONSISTENCY_OUTPUT",
    },
    "mbpp": {
        "label": "MBPP (Mostly Basic Python Problems)",
        "script": "mbpp_test.py",
        "glob": "mbpp_*.json",
        "env_model": "MBPP_MODEL",
        "env_output": "MBPP_OUTPUT",
    },
    "quality": {
        "label": "QuALITY",
        "script": "quality_test.py",
        "glob": "quality_*.json",
        "env_model": "QUALITY_MODEL",
        "env_output": "QUALITY_OUTPUT",
    }
}


def predict_stem(benchmark_key: str, model: str) -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}_{benchmark_key}_{_safe_slug(model)}"


def _newest_match(results_dir: Path, pattern: str, since: float) -> Path | None:
    candidates = [
        p for p in results_dir.glob(pattern)
        if p.stat().st_mtime >= since - 1
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run(benchmark_key: str, model: str, output_stem: str | None = None) -> Path:
    if benchmark_key not in BENCHMARKS:
        raise SystemExit(f"unknown benchmark: {benchmark_key!r}")

    cfg = BENCHMARKS[benchmark_key]
    script = HERE / cfg["script"]
    if not script.is_file():
        raise SystemExit(f"missing runner script: {script}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem or predict_stem(benchmark_key, model)
    log_path = RESULTS_DIR / f"{stem}.log"

    env = os.environ.copy()
    env[cfg["env_model"]] = model
    env[cfg["env_output"]] = str(RESULTS_DIR)
    env.setdefault("TQA_BASE_URL", env.get("DUKE_GATEWAY_URL", "https://litellm.oit.duke.edu/v1"))
    env.setdefault("LITELLM_BASE_URL", env.get("TQA_BASE_URL", "https://litellm.oit.duke.edu/v1"))
    key = (
        env.get("DUKE_GATEWAY_KEY")
        or env.get("OPENAI_API_KEY")
        or env.get("LITELLM_API_KEY")
    )
    if key:
        for k in ("TQA_API_KEY", "LITELLM_API_KEY", "OPENAI_API_KEY"):
            env.setdefault(k, key)

    started = time.time()
    with log_path.open("w", encoding="utf-8") as log_f:
        log_f.write(f"=== benchmark={benchmark_key} model={model!r} ===\n")
        log_f.flush()
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(HERE),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            check=False,
        )
        log_f.write(f"\n=== exit code: {proc.returncode} ===\n")

    if proc.returncode != 0:
        raise SystemExit(proc.returncode)

    src = _newest_match(RESULTS_DIR, cfg["glob"], since=started)
    if src is None:
        raise SystemExit(f"runner finished but no output matching {cfg['glob']!r}")

    dest = RESULTS_DIR / f"{stem}{src.suffix}"
    shutil.copy2(src, dest)
    if src.resolve() != dest.resolve():
        src.unlink()
    log_path.unlink(missing_ok=True)
    return dest


def main() -> int:
    p = argparse.ArgumentParser(description="Run a public benchmark against a gateway model.")
    p.add_argument(
        "--benchmark",
        required=True,
        choices=sorted(BENCHMARKS),
        help="benchmark suite key",
    )
    p.add_argument("--model", required=True, help="exact gateway model id")
    p.add_argument(
        "--output-stem",
        default=None,
        help="stable results filename stem (default: <UTC>_<benchmark>_<model>)",
    )
    args = p.parse_args()
    dest = run(args.benchmark, args.model, args.output_stem)
    print(f"Results: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
