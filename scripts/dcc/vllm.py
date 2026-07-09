"""
DCC vLLM session helpers — start, wait, status, stop.

Usage:
    uv run python -m scripts.dcc.vllm start [--model ...]
    uv run python -m scripts.dcc.vllm wait
    uv run python -m scripts.dcc.vllm status
    uv run python -m scripts.dcc.vllm stop
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DCC_DIR = Path(__file__).resolve().parent
REPO_ROOT = DCC_DIR.parent.parent
STATE_FILE = DCC_DIR / ".vllm-session.env"
# Per-run state files live here so concurrent orchestrations (multiple models
# served/evaluated at once) don't clobber each other's JOB_ID/HOST/PORT. The
# single default STATE_FILE above stays the backward-compatible one-session path
# for the plain `python -m scripts.dcc.vllm start` CLI flow.
JOBS_DIR = DCC_DIR / ".jobs"
SBATCH_TEMPLATE = DCC_DIR / "templates" / "vllm_server.sbatch"

SQUEUE_FORMAT = "%.18i %.10T %.20R %B"


def _write_state(data: dict[str, str], state_file: Path | None = None) -> None:
    # Resolve the module global at CALL time (not as a default arg) so tests that
    # mock.patch STATE_FILE, and callers that pass a per-run path, both work.
    sf = state_file if state_file is not None else STATE_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'{k}="{v}"' for k, v in data.items()]
    sf.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_state(state_file: Path | None = None) -> dict[str, str]:
    sf = state_file if state_file is not None else STATE_FILE
    if not sf.is_file():
        raise FileNotFoundError(f"No vLLM session state file at {sf}")
    data: dict[str, str] = {}
    for line in sf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        data[key.strip()] = val.strip().strip('"')
    return data


def _resolve_state_file(args: argparse.Namespace) -> Path:
    """Per-run state path from --session-file (or $VLLM_STATE_FILE), else the
    single-session default. Keeps the plain CLI flow unchanged."""
    sf = getattr(args, "session_file", None)
    return Path(sf) if sf else STATE_FILE


# A served model id is an HF repo id or local path — only these characters.
# Rejecting anything else stops a comma (or other metachar) in --model from
# injecting extra NAME=VALUE pairs into sbatch's comma-separated --export list
# (e.g. `--model "x,LD_PRELOAD=/tmp/evil.so"`).
_SAFE_MODEL_ID = re.compile(r"^[A-Za-z0-9._/-]+$")


def cmd_start(args: argparse.Namespace) -> int:
    if not _SAFE_MODEL_ID.fullmatch(args.model):
        print(
            f"error: refusing unsafe --model {args.model!r}: only letters, digits, "
            ". _ / - are allowed (an HF repo id or local path).",
            file=sys.stderr,
        )
        return 2
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    export = (
        f"ALL,MODEL={args.model},PORT={args.port},HF_HOME={args.hf_home},"
        f"LOG_DIR={log_dir},DTYPE={args.dtype},REPO_ROOT={REPO_ROOT}"
    )
    sbatch_argv = [
        "sbatch",
        "--parsable",
        "--job-name=vllm-server",
        f"--output={log_dir}/%x-%j.out",
        f"--partition={args.partition}",
        f"--cpus-per-task={args.cpus}",
        f"--mem={args.memory}",
        f"--time={args.wall_time}",
        f"--export={export}",
    ]
    if args.gpu_type:
        sbatch_argv.append(f"--gres=gpu:{args.gpu_type}:{args.gpu_count}")
    else:
        sbatch_argv.append(f"--gres=gpu:{args.gpu_count}")
    if args.account:
        sbatch_argv.append(f"--account={args.account}")
    sbatch_argv.append(str(SBATCH_TEMPLATE))

    result = subprocess.run(sbatch_argv, capture_output=True, text=True, check=True)
    job_id = result.stdout.strip().split(";")[0]

    state_file = _resolve_state_file(args)
    _write_state({
        "JOB_ID": job_id,
        "MODEL": args.model,
        "PORT": str(args.port),
        "LOG_DIR": str(log_dir),
    }, state_file)
    print(f"Submitted vLLM job {job_id}")
    print(f"State file: {state_file}")
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    state_file = _resolve_state_file(args)
    state = _read_state(state_file)
    job_id = state["JOB_ID"]
    port = state["PORT"]
    max_attempts = args.max_attempts
    sleep_s = args.sleep_seconds

    for attempt in range(max_attempts):
        line = subprocess.run(
            ["squeue", "-h", "-j", job_id, "-o", SQUEUE_FORMAT],
            capture_output=True,
            text=True,
        ).stdout.strip()
        if not line:
            print(f"Job {job_id} is no longer in squeue.", file=sys.stderr)
            return 1

        parts = line.split()
        state_col = parts[1] if len(parts) > 1 else ""
        node = parts[3] if len(parts) > 3 else ""
        print(f"Job {job_id} state={state_col} node={node}")

        if state_col == "R" and node and node not in ("(null)", "n/a"):
            url = f"http://{node}:{port}/health"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    if resp.status == 200:
                        print(f"vLLM is ready at http://{node}:{port}/v1")
                        state["HOST"] = node
                        _write_state(state, state_file)
                        return 0
            except (urllib.error.URLError, OSError):
                pass

        time.sleep(sleep_s)

    print(f"Timed out waiting for vLLM job {job_id} to become ready.", file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace) -> int:
    state = _read_state(_resolve_state_file(args))
    subprocess.run(
        ["squeue", "-j", state["JOB_ID"], "-o", SQUEUE_FORMAT],
        check=False,
    )
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state_file = _resolve_state_file(args)
    state = _read_state(state_file)
    subprocess.run(["scancel", state["JOB_ID"]], check=True)
    state_file.unlink(missing_ok=True)
    print(f"Cancelled vLLM job {state['JOB_ID']}")
    return 0


def _add_session_arg(p: argparse.ArgumentParser) -> None:
    """Per-run state file override, shared by every subcommand. Defaults to
    $VLLM_STATE_FILE, then (in the command handlers) the single-session file."""
    p.add_argument(
        "--session-file",
        default=os.environ.get("VLLM_STATE_FILE"),
        help="per-run state file (default: scripts/dcc/.vllm-session.env)",
    )


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="DCC vLLM session management")
    sub = ap.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Submit vLLM Slurm job")
    _add_session_arg(start)
    start.add_argument("--model", default=os.environ.get("MODEL", "Qwen/Qwen2.5-7B-Instruct"))
    start.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    start.add_argument("--hf-home", default=os.environ.get("HF_HOME", f"/work/{os.environ.get('USER', 'user')}/hf_cache"))
    start.add_argument("--partition", default=os.environ.get("PARTITION", "codeplussu2026-gpu"))
    start.add_argument("--gpu-type", default=os.environ.get("GPU_TYPE", ""))
    start.add_argument("--gpu-count", type=int, default=int(os.environ.get("GPU_COUNT", "1")))
    start.add_argument("--cpus", default=os.environ.get("CPUS_PER_TASK", "8"))
    start.add_argument("--memory", default=os.environ.get("MEMORY", "64G"))
    start.add_argument("--wall-time", default=os.environ.get("WALL_TIME", "02:00:00"))
    start.add_argument("--dtype", default=os.environ.get("DTYPE", "bfloat16"))
    start.add_argument("--account", default=os.environ.get("ACCOUNT", "codeplussu2026"))
    start.add_argument("--log-dir", default=os.environ.get("LOG_DIR", str(REPO_ROOT / "logs")))

    wait = sub.add_parser("wait", help="Wait until vLLM health endpoint responds")
    _add_session_arg(wait)
    wait.add_argument("--max-attempts", type=int, default=int(os.environ.get("MAX_ATTEMPTS", "120")))
    wait.add_argument("--sleep-seconds", type=int, default=int(os.environ.get("SLEEP_SECONDS", "10")))

    status = sub.add_parser("status", help="Show Slurm status for current session")
    _add_session_arg(status)
    stop = sub.add_parser("stop", help="Cancel current vLLM job and remove state file")
    _add_session_arg(stop)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.command == "start":
        return cmd_start(args)
    if args.command == "wait":
        return cmd_wait(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "stop":
        return cmd_stop(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
