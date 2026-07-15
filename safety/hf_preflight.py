"""
Hugging Face pre-flight check — gate a safety run on a valid repo id before
any Slurm job, download, or scan starts.

Thin CLI wrapper around ``evaluator.hf_intake.validate``: same allowlist,
gated/architecture/size rules already used by the evaluator's self-serve
intake, reused here so a bad or oversized repo id fails fast instead of
burning a GPU allocation.

Run from repo root:
    uv run python -m safety.hf_preflight <repo_id>
    uv run python -m safety.hf_preflight Qwen/Qwen2.5-3B-Instruct --json
"""

from __future__ import annotations

import argparse
import json
import sys

from evaluator import hf_intake


def check_repo(repo_id: str) -> hf_intake.ValidationResult:
    """Validate ``repo_id`` the same way the evaluator's intake flow does."""
    return hf_intake.validate(repo_id)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Validate a Hugging Face repo id before scanning it.",
    )
    ap.add_argument("repo_id", help="e.g. Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable result on success instead of a text summary",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = check_repo(args.repo_id)

    if not result.ok:
        print(f"[hf_preflight] REJECTED {args.repo_id!r}: {result.error}", file=sys.stderr)
        return 1

    info = result.info
    if args.json:
        print(json.dumps({
            "repo_id": info.repo_id,
            "architectures": info.architectures,
            "num_params": info.num_params,
        }))
    else:
        params = f"{info.num_params / 1e9:.1f}B" if info.num_params else "unknown"
        print(
            f"[hf_preflight] OK {info.repo_id} "
            f"(architecture={info.architectures[0]}, params={params})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
