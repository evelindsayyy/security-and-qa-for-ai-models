#!/usr/bin/env python3
"""
CLI / browser entrypoint for personality tests (BFI today; add keys in test_catalog).

    python run_personality.py --model "GPT 4.1 Mini"
    python run_personality.py --test bfi --model "GPT 4.1 Mini" --output-stem my-run
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
_REPO = HERE.parent
_BENCHMARKS = _REPO / "benchmarks"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_BENCHMARKS) not in sys.path:
    sys.path.insert(0, str(_BENCHMARKS))

from benchmark_progress import write_progress_stub  # noqa: E402
from personality.test_catalog import DEFAULT_TEST_KEY, get_test, validate_test_key  # noqa: E402

RESULTS_DIR = HERE / "results"


def _safe_slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", model.strip())[:80] or "model"


def predict_stem(model: str, test_key: str) -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}_{test_key}_{_safe_slug(model)}"


def _newest_match(results_dir: Path, *, since: float, legacy_glob: str) -> Path | None:
    candidates = [
        p for p in results_dir.glob(legacy_glob)
        if p.stat().st_mtime >= since - 1
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def run(
    model: str,
    output_stem: str | None = None,
    *,
    test_key: str = DEFAULT_TEST_KEY,
    output_dir: str | Path | None = None,
) -> Path:
    err = validate_test_key(test_key)
    if err:
        raise ValueError(err)
    spec = get_test(test_key)

    results_dir = Path(output_dir) if output_dir else RESULTS_DIR
    if not results_dir.is_absolute():
        results_dir = (_REPO / results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    stem = output_stem or predict_stem(model, test_key)
    log_path = results_dir / f"{stem}.log"
    progress_path = results_dir / f"{stem}.progress.json"
    prefix = spec["env_prefix"]

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env[f"{prefix}_MODEL"] = model
    env[f"{prefix}_OUTPUT"] = str(results_dir)
    env[f"{prefix}_OUTPUT_STEM"] = stem
    env["BENCHMARK_PROGRESS_PATH"] = str(progress_path)
    env.setdefault("LITELLM_BASE_URL", env.get("DUKE_GATEWAY_URL", "https://litellm.oit.duke.edu/v1"))
    key = env.get("DUKE_GATEWAY_KEY") or env.get("OPENAI_API_KEY") or env.get("LITELLM_API_KEY")
    if key:
        env.setdefault("LITELLM_API_KEY", key)
        env.setdefault("OPENAI_API_KEY", key)

    write_progress_stub(
        progress_path,
        benchmark_key=test_key,
        benchmark_label=spec["progress_label"],
        model=model,
        total=spec["total_items"],
        unit="items",
        message=f"Starting {spec['short_label']}…",
    )

    started = time.time()
    script = HERE / spec["script"]
    with log_path.open("w", encoding="utf-8") as log_f:
        log_f.write(f"=== test={test_key} model={model!r} ===\n")
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

    dest = results_dir / f"{stem}.json"
    if not dest.is_file():
        src = _newest_match(results_dir, since=started, legacy_glob=spec["legacy_glob"])
        if src is None:
            raise SystemExit(f"{spec['short_label']} runner finished but no output JSON was found")
        shutil.copy2(src, dest)
        if src.resolve() != dest.resolve():
            src.unlink(missing_ok=True)
    else:
        src = _newest_match(results_dir, since=started, legacy_glob=spec["legacy_glob"])
        if src is not None and src.resolve() != dest.resolve():
            src.unlink(missing_ok=True)
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a personality test on an LLM")
    parser.add_argument("--test", default=DEFAULT_TEST_KEY, help="Personality test key (default: bfi)")
    parser.add_argument("--model", required=True, help="Gateway model id")
    parser.add_argument("--output-stem", help="Stable artifact stem for UI polling")
    parser.add_argument("--output-dir", help="Results directory (default: personality/results)")
    args = parser.parse_args()
    path = run(args.model, args.output_stem, test_key=args.test, output_dir=args.output_dir)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
