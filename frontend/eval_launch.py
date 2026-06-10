"""
Launch evaluator runs from the browser ("Start run" button).

Security model (TASK.md hard constraint): every form value is validated
against a server-side allowlist derived from the runner's own pricing
table before anything reaches subprocess. The subprocess is an argv list
(never a shell), so even allowlisted values can't be interpreted.

No queue, no Celery (CLAUDE.md): one in-flight run per parameter combo,
tracked in a module-level registry. A second identical click returns the
in-flight slug instead of spawning a duplicate.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

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

CANDIDATE_MODELS: tuple[str, ...] = tuple(_COST_PER_M_TOKENS.keys())

# Judges the team has actually calibrated (cross-judge experiment, week 4).
JUDGE_MODELS: tuple[str, ...] = ("Llama 4 Maverick", "Llama 3.3", "gpt-oss-120b")

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
    "policy_qa_v1": {
        "label": "Duke policy Q&A (4 questions, draft)",
        "suite": EVALUATOR / "tasks" / "policy_qa_v1.jsonl",
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
    if candidate not in CANDIDATE_MODELS:
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
    return None


def build_command(
    candidate: str, judge: str, suite_key: str, max_tokens: int, stem: str
) -> list[str]:
    """argv for the runner subprocess. List form — never a shell string."""
    cfg = SUITES[suite_key]
    return [
        sys.executable,
        str(RUNNER),
        "--candidate-model", candidate,
        "--judge-model", judge,
        "--suite", str(cfg["suite"]),
        "--rubric", str(cfg["rubric"]),
        "--system-prompt", str(cfg["system_prompt"]),
        "--judge-prompt", str(JUDGE_PROMPT),
        "--max-tokens", str(max_tokens),
        "--output-name", stem,
    ]


def predict_stem(suite_key: str, candidate: str) -> str:
    """Same naming convention the runner uses for its own output files."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}_{suite_key}_{_safe_slug(candidate)}"


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

        stem = predict_stem(suite_key, candidate)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = RESULTS_DIR / f"{stem}.log"
        with log_path.open("wb") as log_f:
            proc = subprocess.Popen(
                build_command(candidate, judge, suite_key, max_tokens, stem),
                cwd=str(EVALUATOR),
                stdout=log_f,
                stderr=subprocess.STDOUT,
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
    return {
        "candidates": list(CANDIDATE_MODELS),
        "judges": list(JUDGE_MODELS),
        "suites": [
            {"key": k, "label": v["label"], "n": suite_question_count(k)}
            for k, v in SUITES.items()
        ],
        "families": {m: model_family(m) for m in (*CANDIDATE_MODELS, *JUDGE_MODELS)},
        "pricing": {m: list(r) for m, r in _COST_PER_M_TOKENS.items()},
        "pricing_json": json.dumps({m: list(r) for m, r in _COST_PER_M_TOKENS.items()}),
        "max_tokens_min": MAX_TOKENS_MIN,
        "max_tokens_max": MAX_TOKENS_MAX,
    }
