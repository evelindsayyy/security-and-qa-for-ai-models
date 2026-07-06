"""
dcc_orchestrate.py — one-call self-serve DCC evaluation.

Chains the four steps that were manual before (each its own command, with the
endpoint glued together by hand):

    validate (hf_intake)  ->  serve (scripts.dcc.vllm start + wait)
        ->  evaluate (runner.py against the vLLM endpoint)  ->  teardown (vllm stop)

Design rules (the reason this module exists rather than a shell script):

  * Teardown ALWAYS runs once a job is submitted — success OR failure — so a
    served model never leaks the GPU when the eval errors. It's in a `finally`.
  * Nothing is torn down that was never started. A validate/start failure returns
    immediately with no `scancel` (there is no job to cancel).
  * Per-run job state lives in ``scripts/dcc/.jobs/<slug>.env`` so two concurrent
    orchestrations don't clobber each other's node/port.
  * ``--dry-run`` prints the exact chain it WOULD run without touching the cluster.
    This dev environment can't reach the Duke DCC; the real run is on-cluster.

The runner is invoked as a SUBPROCESS (as ``frontend/eval_launch.py`` does), not
imported: ``runner.py`` uses flat imports that need ``evaluator/`` on ``sys.path``,
and a subprocess keeps the never-crash-the-run boundary between orchestration and
evaluation — a runner crash becomes a failed result, not a crashed orchestrator.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from evaluator import hf_intake
from scripts.dcc import vllm

EVALUATOR = Path(__file__).resolve().parent
ROOT = EVALUATOR.parent
RUNNER = EVALUATOR / "runner.py"

# Same locked defaults as runner.py, but with the rubric-aware judge prompt
# (v2) so the orchestrator works for any suite, not just it_support's 4 dims.
DEFAULT_SUITE = EVALUATOR / "tasks" / "it_support_v1.jsonl"
DEFAULT_RUBRIC = EVALUATOR / "tasks" / "rubrics" / "it_support.yaml"
DEFAULT_SYSTEM_PROMPT = EVALUATOR / "prompts" / "system" / "it_support_v1.txt"
DEFAULT_JUDGE_PROMPT = EVALUATOR / "prompts" / "judge" / "reference_based_v2.txt"

INFERENCE_BACKEND = "dcc"


@dataclass(frozen=True)
class OrchestrationResult:
    """What happened, for the CLI and (Day 2) the frontend status poller.

    ``phase`` is the last stage reached: validate | serve | evaluate | complete
    | dry_run. ``ok`` is True only for a clean end-to-end run (or a dry run).
    """
    ok: bool
    phase: str
    error: Optional[str] = None
    endpoint: Optional[str] = None
    output_name: Optional[str] = None
    exit_code: Optional[int] = None
    job_state_file: Optional[str] = None
    plan: tuple[str, ...] = ()


def _slug_for(hf_repo: str, slug: Optional[str]) -> str:
    """A filename-safe per-run id for the job state file."""
    if slug:
        return slug
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in hf_repo)
    return f"{ts}_{safe}"


def _runner_argv(
    hf_repo: str,
    endpoint: str,
    *,
    judge_model: str,
    suite: Path,
    rubric: Path,
    system_prompt: Path,
    judge_prompt: Path,
    max_tokens: int,
    judge_max_tokens: int,
    output_name: Optional[str],
) -> list[str]:
    """argv for the runner subprocess (list form — never a shell string).

    The candidate model id IS the HF repo (vLLM serves it under that name), and
    the backend/repo are recorded into the row so a DCC-served result is never
    confused with a Gateway result of the same name.
    """
    argv = [
        sys.executable, str(RUNNER),
        "--candidate-model", hf_repo,
        "--candidate-endpoint", endpoint,
        "--inference-backend", INFERENCE_BACKEND,
        "--hf-repo", hf_repo,
        "--judge-model", judge_model,
        "--suite", str(suite),
        "--rubric", str(rubric),
        "--system-prompt", str(system_prompt),
        "--judge-prompt", str(judge_prompt),
        "--max-tokens", str(max_tokens),
        "--judge-max-tokens", str(judge_max_tokens),
    ]
    if output_name:
        argv += ["--output-name", output_name]
    return argv


def _invoke_runner(
    hf_repo: str,
    endpoint: str,
    *,
    judge_model: str,
    suite: Path,
    rubric: Path,
    system_prompt: Path,
    judge_prompt: Path,
    max_tokens: int,
    judge_max_tokens: int,
    output_name: Optional[str],
) -> int:
    """Run the eval pipeline against the vLLM endpoint; return the exit code.

    cwd is evaluator/ so the runner's flat imports resolve, matching the
    launcher. A seam the tests patch to keep the chain offline.
    """
    argv = _runner_argv(
        hf_repo, endpoint, judge_model=judge_model, suite=suite, rubric=rubric,
        system_prompt=system_prompt, judge_prompt=judge_prompt,
        max_tokens=max_tokens, judge_max_tokens=judge_max_tokens,
        output_name=output_name,
    )
    proc = subprocess.run(argv, cwd=str(EVALUATOR))
    return proc.returncode


def _endpoint_from_state(state_file: Path) -> str:
    """Build the OpenAI-compatible base URL from the state cmd_wait wrote."""
    st = vllm._read_state(state_file)
    host, port = st.get("HOST"), st.get("PORT")
    if not host or not port:
        raise RuntimeError(f"state file {state_file} has no HOST/PORT after wait")
    return f"http://{host}:{port}/v1"


def _teardown(state_file: Path) -> None:
    """Cancel the job and drop the state file. Never raises — a teardown error
    must not mask (or replace) the real orchestration result."""
    try:
        args = vllm.build_parser().parse_args(
            ["stop", "--session-file", str(state_file)]
        )
        vllm.cmd_stop(args)
    except Exception as e:  # noqa: BLE001 — teardown is best-effort
        print(f"  WARN: teardown failed for {state_file}: {e}", file=sys.stderr)


def orchestrate_eval(
    hf_repo: str,
    *,
    judge_model: str,
    suite: Path = DEFAULT_SUITE,
    rubric: Path = DEFAULT_RUBRIC,
    system_prompt: Path = DEFAULT_SYSTEM_PROMPT,
    judge_prompt: Path = DEFAULT_JUDGE_PROMPT,
    max_tokens: int = 2000,
    judge_max_tokens: int = 2000,
    port: int = 8000,
    slug: Optional[str] = None,
    output_name: Optional[str] = None,
    wait_max_attempts: Optional[int] = None,
    wait_sleep_seconds: Optional[int] = None,
    dry_run: bool = False,
) -> OrchestrationResult:
    """Validate -> serve -> evaluate -> teardown, as one fail-safe call."""
    run_slug = _slug_for(hf_repo, slug)
    state_file = vllm.JOBS_DIR / f"{run_slug}.env"

    if dry_run:
        plan = (
            f"validate  hf_intake.validate({hf_repo!r})",
            f"serve     vllm start --model {hf_repo} --port {port} "
            f"--session-file {state_file}",
            f"wait      poll {state_file} until /health -> http://<node>:{port}/v1",
            "evaluate  " + " ".join(_runner_argv(
                hf_repo, f"http://<node>:{port}/v1", judge_model=judge_model,
                suite=suite, rubric=rubric, system_prompt=system_prompt,
                judge_prompt=judge_prompt, max_tokens=max_tokens,
                judge_max_tokens=judge_max_tokens, output_name=output_name)),
            f"teardown  vllm stop --session-file {state_file}",
        )
        for line in plan:
            print(line)
        return OrchestrationResult(
            True, "dry_run", plan=plan, job_state_file=str(state_file)
        )

    # 1) validate — offline allowlist first, then the network fetch (hf_intake).
    #    Runs BEFORE any job is submitted, so a bad repo id costs nothing.
    val = hf_intake.validate(hf_repo)
    if not val.ok:
        return OrchestrationResult(False, "validate", error=val.error)

    # 2) serve — submit the sbatch job. If this fails there is no job, so we
    #    return without teardown.
    start_args = vllm.build_parser().parse_args([
        "start", "--model", hf_repo, "--port", str(port),
        "--session-file", str(state_file),
    ])
    try:
        rc = vllm.cmd_start(start_args)
    except Exception as e:  # noqa: BLE001
        return OrchestrationResult(
            False, "serve", error=f"vLLM start crashed: {e}",
            job_state_file=str(state_file),
        )
    if rc != 0:
        return OrchestrationResult(
            False, "serve", error=f"vLLM start failed (rc={rc})",
            job_state_file=str(state_file),
        )

    # A job now exists — teardown ALWAYS runs from here (finally below).
    try:
        wait_argv = ["wait", "--session-file", str(state_file)]
        if wait_max_attempts is not None:
            wait_argv += ["--max-attempts", str(wait_max_attempts)]
        if wait_sleep_seconds is not None:
            wait_argv += ["--sleep-seconds", str(wait_sleep_seconds)]
        wait_args = vllm.build_parser().parse_args(wait_argv)

        try:
            rc = vllm.cmd_wait(wait_args)
        except Exception as e:  # noqa: BLE001
            return OrchestrationResult(
                False, "serve", error=f"vLLM wait crashed: {e}",
                job_state_file=str(state_file),
            )
        if rc != 0:
            return OrchestrationResult(
                False, "serve", error="vLLM did not become ready",
                job_state_file=str(state_file),
            )

        endpoint = _endpoint_from_state(state_file)

        # 3) evaluate — the existing pipeline, pointed at the vLLM endpoint.
        try:
            exit_code = _invoke_runner(
                hf_repo, endpoint, judge_model=judge_model, suite=suite,
                rubric=rubric, system_prompt=system_prompt,
                judge_prompt=judge_prompt, max_tokens=max_tokens,
                judge_max_tokens=judge_max_tokens, output_name=output_name,
            )
        except Exception as e:  # noqa: BLE001
            return OrchestrationResult(
                False, "evaluate", error=f"runner crashed: {e}",
                endpoint=endpoint, job_state_file=str(state_file),
            )
        if exit_code != 0:
            return OrchestrationResult(
                False, "evaluate", error=f"runner exited {exit_code}",
                endpoint=endpoint, exit_code=exit_code, output_name=output_name,
                job_state_file=str(state_file),
            )
        return OrchestrationResult(
            True, "complete", endpoint=endpoint, exit_code=0,
            output_name=output_name, job_state_file=str(state_file),
        )
    finally:
        # 4) teardown — always, now that a job was submitted.
        _teardown(state_file)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Self-serve DCC eval: validate an HF model, serve it on the "
                    "DCC, run the eval suite against it, then tear the job down.",
    )
    p.add_argument("--hf-repo", required=True,
                   help="Hugging Face repo id to serve + evaluate")
    p.add_argument("--judge-model", required=True,
                   help="Gateway judge model (must differ in family)")
    p.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    p.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    p.add_argument("--system-prompt", type=Path, default=DEFAULT_SYSTEM_PROMPT)
    p.add_argument("--judge-prompt", type=Path, default=DEFAULT_JUDGE_PROMPT)
    p.add_argument("--max-tokens", type=int, default=2000)
    p.add_argument("--judge-max-tokens", type=int, default=2000)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--slug", default=None,
                   help="per-run id for the job state file (default: timestamped)")
    p.add_argument("--output-name", default=None,
                   help="results filename stem (default: the runner's own naming)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the chain without touching the cluster")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    a = _parse_args(argv)
    res = orchestrate_eval(
        a.hf_repo, judge_model=a.judge_model, suite=a.suite, rubric=a.rubric,
        system_prompt=a.system_prompt, judge_prompt=a.judge_prompt,
        max_tokens=a.max_tokens, judge_max_tokens=a.judge_max_tokens,
        port=a.port, slug=a.slug, output_name=a.output_name, dry_run=a.dry_run,
    )
    if res.ok:
        if res.phase != "dry_run":
            print(f"\nOK — {res.phase}"
                  + (f"; output-name={res.output_name}" if res.output_name else ""))
        return 0
    print(f"\nFAILED at {res.phase}: {res.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
