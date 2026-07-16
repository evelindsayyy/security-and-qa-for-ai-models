#!/usr/bin/env python3
"""
Unified entrypoint for public benchmark runners (browser + Docker + CLI).

Wraps the individual *_test.py scripts Jack authored under benchmarks/.
Sets model/output env vars, runs the script, then copies the newest output to a
stable stem so the frontend can poll ``results/<stem>.{json,jsonl}``.

Usage:
    python run_benchmark.py --benchmark truthfulqa --model "GPT 4.1 Mini"
    python run_benchmark.py --benchmark ifeval --model "gpt-5-chat" --output-stem my-run
    python run_benchmark.py --benchmark mmlu --model "GPT 4.1 Mini" --sample 50 --seed 42
    python run_benchmark.py --benchmark ifeval --model "GPT 4.1 Mini" \\
        --output-dir frontend/benchmark_refs --output-stem gpt-4.1-mini-ifeval
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
_REPO = HERE.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from benchmark_run_stats import merge_wall_time  # noqa: E402
from benchmark_progress import write_progress_stub  # noqa: E402


def _safe_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model.strip())[:80] or "model"


BENCHMARKS: dict[str, dict] = {
    "truthfulqa": {
        "label": "TruthfulQA MCQ",
        "script": "tqa_test.py",
        "glob": "tqa_*.json",
        "env_model": "TQA_MODEL",
        "env_output": "TQA_OUTPUT",
        "sample": {"env": "TQA_LIMIT", "label": "Questions", "unit": "questions", "default": 50, "max": 817},
    },
    "ifeval": {
        "label": "IFEval",
        "script": "if_test.py",
        "glob": "ifeval_*.jsonl",
        "env_model": "IFEVAL_MODEL",
        "env_output": "IFEVAL_OUTPUT",
        "sample": {"env": "IFEVAL_SAMPLE", "label": "Prompts", "unit": "prompts", "default": 20, "max": 500},
        "seed": {"env": "IFEVAL_SEED", "default": 42},
    },
    "mmlu": {
        "label": "MMLU (Massive Multitask Language Understanding)",
        "script": "mmlu_test.py",
        "glob": "mmlu_*.json",
        "env_model": "MMLU_MODEL",
        "env_output": "MMLU_OUTPUT",
        "sample": {"env": "MMLU_SAMPLE", "label": "Questions", "unit": "questions", "default": 100, "max": 14000},
        "seed": {"env": "MMLU_SEED", "default": 42},
    },
    "tomi": {
        "label": "ToMi (Theory of Mind)",
        "script": "tomi_test.py",
        "glob": "tomi_*.json",
        "env_model": "TOMI_MODEL",
        "env_output": "TOMI_OUTPUT",
        "sample": {"env": "TOMI_LIMIT", "label": "Stories", "unit": "stories", "default": 20, "max": 2000},
    },
    "consistency": {
        "label": "Consistency",
        "script": "consistency_test.py",
        "glob": "consistency_*.json",
        "env_model": "CONSISTENCY_MODEL",
        "env_output": "CONSISTENCY_OUTPUT",
        "sample": {"env": "CONSISTENCY_LIMIT", "label": "Topics", "unit": "topics", "default": 5, "max": 50},
    },
    "mbpp": {
        "label": "MBPP (Mostly Basic Python Problems)",
        "script": "mbpp_test.py",
        "glob": "mbpp_*.json",
        "env_model": "MBPP_MODEL",
        "env_output": "MBPP_OUTPUT",
        "sample": {"env": "MBPP_SAMPLE", "label": "Problems", "unit": "problems", "default": 50, "max": 500},
        "seed": {"env": "MBPP_SEED", "default": 42},
    },
    "quality": {
        "label": "QuALITY",
        "script": "quality_test.py",
        "glob": "quality_*.json",
        "env_model": "QUALITY_MODEL",
        "env_output": "QUALITY_OUTPUT",
        "sample": {"env": "QUALITY_SAMPLE", "label": "Articles", "unit": "articles", "default": 3, "max": 200},
        "seed": {"env": "QUALITY_SEED", "default": 42},
    },
}


def benchmark_options_schema() -> dict[str, dict]:
    """Per-benchmark sample/seed metadata for the frontend."""
    out: dict[str, dict] = {}
    for key, cfg in BENCHMARKS.items():
        entry: dict = {}
        if "sample" in cfg:
            entry["sample"] = dict(cfg["sample"])
        if "seed" in cfg:
            entry["seed"] = dict(cfg["seed"])
        out[key] = entry
    return out


def predict_stem(benchmark_key: str, model: str) -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}_{benchmark_key}_{_safe_slug(model)}"


def _apply_run_options(
    env: dict[str, str],
    cfg: dict,
    *,
    sample: int | None,
    seed: int | None,
) -> None:
    if sample is not None and "sample" in cfg:
        env[cfg["sample"]["env"]] = str(sample)
    if seed is not None and "seed" in cfg:
        env[cfg["seed"]["env"]] = str(seed)


def _expected_total(cfg: dict, env: dict[str, str], sample: int | None) -> int:
    sample_cfg = cfg.get("sample")
    if not sample_cfg:
        return 0
    if sample is not None:
        return max(0, int(sample))
    raw = env.get(sample_cfg["env"])
    if raw is not None and str(raw).strip().isdigit():
        return max(0, int(raw))
    return max(0, int(sample_cfg.get("default", 0)))


def _newest_match(results_dir: Path, pattern: str, since: float) -> Path | None:
    candidates = [
        p for p in results_dir.glob(pattern)
        if p.stat().st_mtime >= since - 1
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _merge_wall_into_stats_file(stats_path: Path, wall_sec: float) -> None:
    if not stats_path.is_file():
        return
    try:
        meta = json.loads(stats_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    meta["wall_time_sec"] = round(wall_sec, 2)
    stats_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _post_process_results(dest: Path, wall_sec: float, stats_path: Path | None = None) -> None:
    """Merge wall-clock time into JSON summary or jsonl sidecar stats."""
    wall_sec = round(wall_sec, 2)
    if dest.suffix == ".json":
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for key in ("summary", "metrics"):
            block = data.get(key)
            if isinstance(block, dict):
                merge_wall_time(block, wall_sec)
                dest.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                return

    if stats_path is not None:
        _merge_wall_into_stats_file(stats_path, wall_sec)


def _resolve_output_dir(path: str | Path | None) -> Path:
    if path is None:
        return RESULTS_DIR
    p = Path(path)
    if not p.is_absolute():
        p = (_REPO / p).resolve()
    return p


def run(
    benchmark_key: str,
    model: str,
    output_stem: str | None = None,
    *,
    sample: int | None = None,
    seed: int | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    if benchmark_key not in BENCHMARKS:
        raise SystemExit(f"unknown benchmark: {benchmark_key!r}")

    cfg = BENCHMARKS[benchmark_key]
    script = HERE / cfg["script"]
    if not script.is_file():
        raise SystemExit(f"missing runner script: {script}")

    results_dir = _resolve_output_dir(output_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = output_stem or predict_stem(benchmark_key, model)
    log_path = results_dir / f"{stem}.log"
    stats_path = results_dir / f"{stem}.stats.json"
    progress_path = results_dir / f"{stem}.progress.json"

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env[cfg["env_model"]] = model
    env[cfg["env_output"]] = str(results_dir)
    env["BENCHMARK_STATS_PATH"] = str(stats_path)
    env["BENCHMARK_PROGRESS_PATH"] = str(progress_path)
    _apply_run_options(env, cfg, sample=sample, seed=seed)
    env.setdefault("TQA_BASE_URL", env.get("DUKE_GATEWAY_URL", "https://litellm.oit.duke.edu/v1"))
    env.setdefault("LITELLM_BASE_URL", env.get("TQA_BASE_URL", "https://litellm.oit.duke.edu/v1"))
    key = (
        env.get("DUKE_GATEWAY_KEY")
        or env.get("OPENAI_API_KEY")
        or env.get("LITELLM_API_KEY")
        or env.get("HF_TOKEN")
        or env.get("HUGGINGFACE_TOKEN")
    )
    if key:
        for k in ("TQA_API_KEY", "LITELLM_API_KEY", "OPENAI_API_KEY"):
            env.setdefault(k, key)

    sample_cfg = cfg.get("sample") or {}
    write_progress_stub(
        progress_path,
        benchmark_key=benchmark_key,
        benchmark_label=cfg["label"],
        model=model,
        total=_expected_total(cfg, env, sample),
        unit=str(sample_cfg.get("unit", "items")),
    )

    started = time.time()
    with log_path.open("w", encoding="utf-8") as log_f:
        log_f.write(f"=== benchmark={benchmark_key} model={model!r} ===\n")
        if sample is not None:
            log_f.write(f"=== sample={sample} ===\n")
        if seed is not None:
            log_f.write(f"=== seed={seed} ===\n")
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

    wall_sec = time.time() - started

    if proc.returncode != 0:
        raise SystemExit(proc.returncode)

    src = _newest_match(results_dir, cfg["glob"], since=started)
    if src is None:
        raise SystemExit(f"runner finished but no output matching {cfg['glob']!r}")

    dest = results_dir / f"{stem}{src.suffix}"
    shutil.copy2(src, dest)
    if src.resolve() != dest.resolve():
        src.unlink()

    # Promote runner-written stats sidecar to stable stem when needed.
    runner_stats = src.parent / f"{src.stem}.stats.json"
    if runner_stats.is_file() and runner_stats != stats_path:
        shutil.copy2(runner_stats, stats_path)
        runner_stats.unlink(missing_ok=True)

    _post_process_results(dest, wall_sec, stats_path=stats_path)
    progress_path.unlink(missing_ok=True)

    try:
        log_path.unlink(missing_ok=True)
    except OSError:
        pass
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
    p.add_argument(
        "--output-dir",
        default=None,
        help="output directory (default: benchmarks/results; repo-relative paths ok)",
    )
    p.add_argument(
        "--sample",
        type=int,
        default=None,
        help="override default sample size for this benchmark",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed where the benchmark supports it",
    )
    args = p.parse_args()
    dest = run(
        args.benchmark,
        args.model,
        args.output_stem,
        sample=args.sample,
        seed=args.seed,
        output_dir=args.output_dir,
    )
    print(f"Results: {dest}")
    from dbutils.post_run import maybe_sync_artifact

    maybe_sync_artifact(dest, "benchmark")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
