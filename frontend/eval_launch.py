"""
Launch evaluator runs from the browser ("Start run" button).

Security model (TASK.md hard constraint): every form value is validated
against a server-side allowlist before anything reaches subprocess. The
candidate allowlist is the **live gateway catalog** (chat models) so the
dropdown stays current without hardcoded ids; the pricing table is only a
cost annotation. The subprocess is an argv list (never a shell), so even
allowlisted values can't be interpreted.

No queue, no Celery (CLAUDE.md): one in-flight run per parameter combo,
tracked in a module-level registry. A second identical click returns the
in-flight slug instead of spawning a duplicate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from frontend import docker_launch
from frontend.path_safety import is_safe_slug

ROOT = Path(__file__).parent.parent
EVALUATOR = ROOT / "evaluator"
RESULTS_DIR = EVALUATOR / "results"
RUNNER = EVALUATOR / "runner.py"

# evaluator/ isn't a package; same sys.path approach as eval_run_data.py.
sys.path.insert(0, str(EVALUATOR))

from runner import _COST_PER_M_TOKENS, _safe_slug  # noqa: E402

# ---------------------------------------------------------------------------
# Allowlists — the security boundary for POST /eval-run/start
# ---------------------------------------------------------------------------

# Candidate categories eligible for the IT-support/chat suites.
_CANDIDATE_CATEGORIES = frozenset({"general_chat"})

# Offline fallback (gateway unreachable): the curated/priced known-good set.
_CANDIDATE_FALLBACK: tuple[str, ...] = tuple(_COST_PER_M_TOKENS.keys())


def candidate_models() -> tuple[str, ...]:
    """Live chat models from the gateway catalog; priced set if offline."""
    try:
        from gateway.catalog import eligible_models

        ids = eligible_models(_CANDIDATE_CATEGORIES)
    except Exception:  # noqa: BLE001 — never break the form on a gateway hiccup
        ids = []
    return tuple(ids) if ids else _CANDIDATE_FALLBACK


# Judges the team has actually calibrated (cross-judge experiment, week 4).
# Per docs/judge-selection.md (interim decision, week 4): Maverick is the
# primary judge, gpt-oss-120b the strict spot-check for Llama candidates.
# Llama 3.3 was dropped — leniency ceiling (all 5s on strong candidates).
JUDGE_MODELS: tuple[str, ...] = ("Llama 4 Maverick", "gpt-oss-120b")

# MT-Bench rule: judge must come from a different model family than the
# candidate. Family is derived from the Gateway id prefix.
def model_family(model: str) -> str:
    return "meta" if model.lower().startswith("llama") else "openai"


# Suite key -> contract files. Rubric/prompt pairing lives here so the
# form can't produce the judge-prompt/rubric mismatch the runner rejects.
SUITES: dict[str, dict] = {
    "it_support_v1": {
        "label": "IT support (12 questions, locked)",
        "suite": EVALUATOR / "tasks" / "it_support_v1.jsonl",
        "rubric": EVALUATOR / "tasks" / "rubrics" / "it_support.yaml",
        "system_prompt": EVALUATOR / "prompts" / "system" / "it_support_v1.txt",
    },
    "policy_qa_v1.1": {
        "label": "Duke policy Q&A (12 questions, draft)",
        "suite": EVALUATOR / "tasks" / "policy_qa_v1.1.jsonl",
        "rubric": EVALUATOR / "tasks" / "rubrics" / "policy_qa_v1.yaml",
        "system_prompt": EVALUATOR / "prompts" / "system" / "it_support_v1.txt",
    },
}

# reference_based_v2 builds its output schema from the rubric, so it works
# for every suite; v1 only matches it_support's four dimensions.
JUDGE_PROMPT = EVALUATOR / "prompts" / "judge" / "reference_based_v2.txt"

MAX_TOKENS_MIN, MAX_TOKENS_MAX = 50, 4000

# slug -> Popen for in-flight runs; param-combo key -> slug for dedupe.
_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()


def suite_question_count(suite_key: str) -> int:
    """Number of questions in a suite (line 0 is metadata)."""
    lines = SUITES[suite_key]["suite"].read_text(encoding="utf-8").splitlines()
    return sum(1 for line in lines[1:] if line.strip())


def validate_launch(
    candidate: str, judge: str, suite_key: str, max_tokens: int
) -> str | None:
    """Return an error message, or None if the launch request is valid."""
    if candidate not in candidate_models():
        return f"candidate model not in allowlist: {candidate!r}"
    if judge not in JUDGE_MODELS:
        return f"judge model not in allowlist: {judge!r}"
    if model_family(judge) == model_family(candidate):
        return (
            f"judge {judge!r} is the same model family as candidate "
            f"{candidate!r} — cross-family judging required (MT-Bench rule)"
        )
    if suite_key not in SUITES:
        return f"unknown suite: {suite_key!r}"
    if not (MAX_TOKENS_MIN <= max_tokens <= MAX_TOKENS_MAX):
        return f"max_tokens must be {MAX_TOKENS_MIN}-{MAX_TOKENS_MAX}"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("evaluator")
    return None


def _container_rel(path: Path) -> str:
    """Path inside the evaluator Docker image (WORKDIR /app/evaluator)."""
    return str(path.relative_to(EVALUATOR)).replace("\\", "/")


def build_command(
    candidate: str, judge: str, suite_key: str, max_tokens: int, stem: str
) -> list[str]:
    """argv for the runner subprocess. List form — never a shell string."""
    cfg = SUITES[suite_key]
    inner = [
        "python",
        "runner.py",
        "--candidate-model",
        candidate,
        "--judge-model",
        judge,
        "--suite",
        _container_rel(cfg["suite"]),
        "--rubric",
        _container_rel(cfg["rubric"]),
        "--system-prompt",
        _container_rel(cfg["system_prompt"]),
        "--judge-prompt",
        _container_rel(JUDGE_PROMPT),
        "--max-tokens",
        str(max_tokens),
        "--judge-max-tokens",
        "2000",
        "--output-name",
        stem,
    ]
    if docker_launch.use_docker():
        return docker_launch.compose_run_argv("evaluator", inner)
    return [
        sys.executable,
        str(RUNNER),
        "--candidate-model",
        candidate,
        "--judge-model",
        judge,
        "--suite",
        str(cfg["suite"]),
        "--rubric",
        str(cfg["rubric"]),
        "--system-prompt",
        str(cfg["system_prompt"]),
        "--judge-prompt",
        str(JUDGE_PROMPT),
        "--max-tokens",
        str(max_tokens),
        "--judge-max-tokens",
        "2000",
        "--output-name",
        stem,
    ]


def predict_stem(suite_key: str, candidate: str) -> str:
    """Same naming convention the runner uses for its own output files."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}_{suite_key}_{_safe_slug(candidate)}"


def _wipe_prior_runs(suite_key: str, candidate: str) -> None:
    """Delete previous result/trace/log files for this (suite, candidate).

    Runner output is timestamped, so old runs would otherwise pile up in the
    comparison table (e.g. a stale "12/12 empty" row next to a fixed one).
    Wiping on launch keeps exactly one run per model+suite on disk.
    """
    suffix = f"_{suite_key}_{_safe_slug(candidate)}"
    for path in RESULTS_DIR.glob(f"*{suffix}*"):
        if path.suffix in (".jsonl", ".log"):
            path.unlink(missing_ok=True)


def start_run(
    candidate: str, judge: str, suite_key: str, max_tokens: int
) -> tuple[str, bool]:
    """Spawn a runner subprocess. Returns (slug, was_already_running).

    Caller must have passed validate_launch first; this function assumes
    allowlisted inputs.
    """
    combo = (candidate, judge, suite_key, max_tokens)
    with _LOCK:
        existing = _INFLIGHT.get(combo)
        if existing and _RUNNING.get(existing) is not None \
                and _RUNNING[existing].poll() is None:
            return existing, True

        # Fresh run — drop prior outputs for this model+suite so the table
        # shows one current result instead of accumulating stale runs.
        _wipe_prior_runs(suite_key, candidate)

        if docker_launch.use_docker():
            docker_launch.ensure_stack("evaluator")

        stem = predict_stem(suite_key, candidate)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RESULTS_DIR / f"{stem}.log"
        cmd = build_command(candidate, judge, suite_key, max_tokens, stem)
        with log_path.open("wb") as log_f:
            log_f.write(f"=== command: {' '.join(cmd)} ===\n".encode())
            # PYTHONUNBUFFERED: stream the runner's stdout into the log as it
            # happens — without it, a killed process loses everything Python
            # had buffered (observed: a .log with only this header line).
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT if docker_launch.use_docker() else EVALUATOR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                env=env,
                # Own process group: stopping/restarting the Flask dev server
                # must not kill an in-flight run (it writes one row per
                # question, so orphaned completion is safe and useful).
                start_new_session=True,
            )
        _RUNNING[stem] = proc
        _INFLIGHT[combo] = stem
        return stem, False


def get_status(slug: str) -> dict:
    """Run status from the JSONL on disk + the process registry.

    complete: file has one row per suite question
    running:  process alive (or file growing)
    failed:   process exited non-zero, or exited with an incomplete file
    """
    if not is_safe_slug(slug):
        return {"status": "not_found", "progress": 0, "total": 0}

    suite_key = next((k for k in SUITES if f"_{k}_" in f"_{slug}_"), None)
    total = suite_question_count(suite_key) if suite_key else 0

    path = RESULTS_DIR / f"{slug}.jsonl"
    progress = 0
    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            progress = sum(1 for line in f if line.strip())

    if total and progress >= total:
        return {"status": "complete", "progress": progress, "total": total}

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return {"status": "running", "progress": progress, "total": total}
    if proc is not None:  # exited without a complete file
        return {"status": "failed", "progress": progress, "total": total}
    if path.is_file():
        # partial file, no registered process (e.g. Flask restarted mid-run)
        return {"status": "failed", "progress": progress, "total": total}
    return {"status": "not_found", "progress": 0, "total": total}


def get_launch_options() -> dict:
    """Everything the /eval-run/new form needs to render."""
    candidates = candidate_models()
    return {
        "candidates": list(candidates),
        "judges": list(JUDGE_MODELS),
        "suites": [
            {"key": k, "label": v["label"], "n": suite_question_count(k)}
            for k, v in SUITES.items()
        ],
        "families": {m: model_family(m) for m in (*candidates, *JUDGE_MODELS)},
        "pricing": {m: list(r) for m, r in _COST_PER_M_TOKENS.items()},
        "pricing_json": json.dumps({m: list(r) for m, r in _COST_PER_M_TOKENS.items()}),
        "max_tokens_min": MAX_TOKENS_MIN,
        "max_tokens_max": MAX_TOKENS_MAX,
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
    }
