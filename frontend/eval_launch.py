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
from frontend.launch_registry import check_inflight_combo
from frontend.log_status import run_log_payload, status_message
from frontend.path_safety import is_safe_slug
from frontend.run_paths import inflight_scope_key

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
# Maverick is the primary judge; gpt-oss-120b the strict spot-check for Llama
# candidates. Llama 3.3 was dropped — leniency ceiling (all 5s on strong
# candidates).
# OpenAI judges re-enabled 2026-06-22: the gateway metadata/store bug that 400'd
# all OpenAI models was fixed; GPT 4.1 Mini + gpt-5-chat verified to return
# valid judge JSON (the bar gpt-oss-120b fails ~75% of the time), and both are
# non-reasoning chat models (no hidden-thinking-token risk). Mentor approved
# 2026-06-22 for gateway-hosted OpenAI only; recorded in docs/judge-selection.md.
JUDGE_MODELS: tuple[str, ...] = (
    "Llama 4 Maverick", "GPT 4.1 Mini", "gpt-5-chat", "gpt-oss-120b",
)

# MT-Bench rule: the judge must come from a different model family than the
# candidate. The family is matched by keyword ANYWHERE in the id (case-
# insensitive), so variants like "meta-llama/Llama-4-Scout" or "Meta-Llama-3.1"
# classify as meta — not just ids that literally start with "llama" (a naive
# prefix check let a Llama candidate + Llama judge slip past the cross-family
# rule when the Gateway returned a Hub-style id). gpt-oss-* stays "openai" (it IS
# an OpenAI model, so self-preference still applies vs gpt-*).
def model_family(model: str) -> str:
    m = model.lower()
    if "llama" in m:
        return "meta"
    if "qwen" in m:
        return "qwen"
    if "mistral" in m or "mixtral" in m:
        return "mistral"
    if "gemma" in m:
        return "google"
    if "gpt" in m or "openai" in m or m.startswith(("o1", "o3", "o4")):
        return "openai"
    return "other"


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
    "summarization_v1": {
        "label": "Document summarization (6 docs, pilot)",
        "suite": EVALUATOR / "tasks" / "summarization_v1.jsonl",
        "rubric": EVALUATOR / "tasks" / "rubrics" / "summarization_v1.yaml",
        "system_prompt": EVALUATOR / "prompts" / "system" / "summarization_v1.txt",
    },
}

# reference_based_v2 builds its output schema from the rubric, so it works
# for every suite; v1 only matches it_support's four dimensions.
JUDGE_PROMPT = EVALUATOR / "prompts" / "judge" / "reference_based_v2.txt"

MAX_TOKENS_MIN, MAX_TOKENS_MAX = 50, 4000

# --- Custom ("bring your own") question sets -------------------------------
# Users who don't like our reference suites can supply their own questions +
# references. A custom run writes a one-off suite file under tasks/custom/ and
# runs the normal pipeline against it. These runs are ad-hoc, NOT a locked
# comparable suite — they're versioned `custom_<ts>` and kept out of the main
# /eval-run comparison table so they never pollute cross-model comparability.
CUSTOM_SUITES_DIR = EVALUATOR / "tasks" / "custom"
CUSTOM_RUBRIC = EVALUATOR / "tasks" / "rubrics" / "it_support.yaml"  # general dims
CUSTOM_SYSTEM_PROMPT = EVALUATOR / "prompts" / "system" / "generic_v1.txt"
CUSTOM_MAX_QUESTIONS = 50
CUSTOM_MAX_FIELD_CHARS = 8000  # per question / per reference
CUSTOM_PREFIX = "custom_"

# slug -> Popen for in-flight runs; param-combo key -> slug for dedupe.
_RUNNING: dict[str, subprocess.Popen] = {}
_INFLIGHT: dict[tuple, str] = {}
_LOCK = threading.Lock()


def _suite_cfg(suite_key: str) -> dict | None:
    """Resolve a suite key to its contract files. Returns None for unknown
    keys. Handles both curated SUITES and saved custom suites
    (`custom_<ts>` → tasks/custom/<key>.jsonl with the general rubric)."""
    if suite_key in SUITES:
        return SUITES[suite_key]
    if suite_key.startswith(CUSTOM_PREFIX):
        path = CUSTOM_SUITES_DIR / f"{suite_key}.jsonl"
        if path.is_file():
            return {
                "label": "Custom questions",
                "suite": path,
                "rubric": CUSTOM_RUBRIC,
                "system_prompt": CUSTOM_SYSTEM_PROMPT,
            }
    return None


def _all_suite_keys() -> list[str]:
    """Curated suite keys plus any saved custom suites."""
    custom = []
    if CUSTOM_SUITES_DIR.is_dir():
        custom = sorted(p.stem for p in CUSTOM_SUITES_DIR.glob(f"{CUSTOM_PREFIX}*.jsonl"))
    return list(SUITES) + custom


def suite_question_count(suite_key: str) -> int:
    """Number of questions in a suite (line 0 is metadata)."""
    cfg = _suite_cfg(suite_key)
    if cfg is None:
        return 0
    lines = cfg["suite"].read_text(encoding="utf-8").splitlines()
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
    if _suite_cfg(suite_key) is None:
        return f"unknown suite: {suite_key!r}"
    if not (MAX_TOKENS_MIN <= max_tokens <= MAX_TOKENS_MAX):
        return f"max_tokens must be {MAX_TOKENS_MIN}-{MAX_TOKENS_MAX}"
    if docker_launch.use_docker() and not docker_launch.docker_available():
        return docker_launch.docker_required_message("evaluator")
    return None


# Suggested open-weight models for the HF-model launcher field (datalist hints).
SUGGESTED_HF_REPOS: tuple[str, ...] = (
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "meta-llama/Llama-3.2-1B-Instruct",
    "gpt2",
)


def validate_hf_candidate(repo_id: str) -> dict:
    """Validate a user-supplied Hugging Face model for evaluation (link path).

    Wraps evaluator/hf_intake — checks the repo exists, is open, is vLLM-servable,
    and fits the GPU. Shapes the verdict for eval_run_new.html. Serving + running
    an HF model is the DCC-orchestration milestone; here we validate before it."""
    from evaluator import hf_intake

    res = hf_intake.validate(repo_id)
    info = res.info
    return {
        "ok": res.ok,
        "error": res.error,
        "repo_id": repo_id,
        "architectures": info.architectures if info else None,
        "num_params": info.num_params if info else None,
    }


def _container_rel(path: Path) -> str:
    """Path inside the evaluator Docker image (WORKDIR /app/evaluator)."""
    return str(path.relative_to(EVALUATOR)).replace("\\", "/")


def build_command(
    candidate: str, judge: str, suite_key: str, max_tokens: int, stem: str
) -> list[str]:
    """argv for the runner subprocess. List form — never a shell string."""
    cfg = _suite_cfg(suite_key)

    def _flags(suite_p: str, rubric_p: str, system_p: str, judge_p: str) -> list[str]:
        return [
            "--candidate-model", candidate,
            "--judge-model", judge,
            "--suite", suite_p,
            "--rubric", rubric_p,
            "--system-prompt", system_p,
            "--judge-prompt", judge_p,
            "--max-tokens", str(max_tokens),
            "--judge-max-tokens", "2000",
            "--output-name", stem,
        ]

    if docker_launch.use_docker():
        # Container-relative paths (WORKDIR /app/evaluator); only computed here.
        inner = ["python", "runner.py", *_flags(
            _container_rel(cfg["suite"]),
            _container_rel(cfg["rubric"]),
            _container_rel(cfg["system_prompt"]),
            _container_rel(JUDGE_PROMPT),
        )]
        return docker_launch.compose_run_argv("evaluator", inner)
    return [sys.executable, str(RUNNER), *_flags(
        str(cfg["suite"]), str(cfg["rubric"]),
        str(cfg["system_prompt"]), str(JUDGE_PROMPT),
    )]


def predict_stem(suite_key: str, candidate: str) -> str:
    """Same naming convention the runner uses for its own output files."""
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}_{suite_key}_{_safe_slug(candidate)}"


def _stem_from_artifact_path(path: Path) -> str:
    name = path.name
    for suffix in ("_trace.jsonl", ".jsonl", ".log"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _wipe_prior_runs(
    suite_key: str, candidate: str, *, visibility: str, owner_user_id: str | None
) -> None:
    """Delete previous result/trace/log files for this (suite, candidate)
    **in the same visibility/owner scope only** — never touch another
    user's, or the public catalog's, run for the same model+suite.

    Runner output is timestamped, so old runs would otherwise pile up in the
    comparison table (e.g. a stale "12/12 empty" row next to a fixed one).
    Wiping on launch keeps exactly one run per model+suite per scope.
    """
    from dbutils.run_meta import read_run_meta_for_pillar

    suffix = f"_{suite_key}_{_safe_slug(candidate)}"
    for path in RESULTS_DIR.glob(f"*{suffix}*"):
        if path.suffix not in (".jsonl", ".log"):
            continue
        stem = _stem_from_artifact_path(path)
        meta = read_run_meta_for_pillar(RESULTS_DIR / stem, pillar="eval")
        if (meta.get("visibility") or "public") != visibility:
            continue
        if visibility == "private" and meta.get("owner_user_id") != owner_user_id:
            continue
        path.unlink(missing_ok=True)


def start_run(
    candidate: str, judge: str, suite_key: str, max_tokens: int
) -> tuple[str, bool, str]:
    """Spawn a runner subprocess. Returns (slug, was_already_running, visibility).

    Caller must have passed validate_launch first; this function assumes
    allowlisted inputs.
    """
    from frontend.run_launch import build_launch_plan, persist_run_meta_dir, reused_slug

    force_private = suite_key.startswith(CUSTOM_PREFIX)
    plan = build_launch_plan(
        "eval",
        force_private=force_private,
        candidate=candidate,
        judge=judge,
        suite_key=suite_key,
        max_tokens=max_tokens,
    )
    if plan.reused:
        stem = reused_slug(plan) or predict_stem(suite_key, candidate)
        return stem, True, plan.visibility

    combo = (
        candidate, judge, suite_key, max_tokens,
        *inflight_scope_key(plan.visibility, plan.owner_user_id),
    )
    with _LOCK:
        existing = check_inflight_combo(_RUNNING, _INFLIGHT, combo)
        if existing:
            return existing, True, plan.visibility

        # Fresh run — drop prior outputs for this model+suite (same scope
        # only) so the table shows one current result instead of
        # accumulating stale runs.
        _wipe_prior_runs(
            suite_key, candidate, visibility=plan.visibility, owner_user_id=plan.owner_user_id
        )

        if docker_launch.use_docker():
            docker_launch.ensure_stack("evaluator")

        stem = predict_stem(suite_key, candidate)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        persist_run_meta_dir(RESULTS_DIR / stem, plan)
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
        return stem, False, plan.visibility


def get_status(
    slug: str, *, visibility: str = "public", owner_user_id: str | None = None
) -> dict:
    """Run status from the results artifact + the process registry.

    complete: file has one row per suite question
    running:  process alive (or file growing)
    failed:   process exited non-zero, or exited with an incomplete file

    ``visibility``/``owner_user_id`` are accepted for signature parity with
    the other three pillars' ``get_status`` (routes.py calls all four the
    same way) — eval's result path is a globally-unique timestamped stem
    regardless of visibility, so there's no separate location to resolve.
    """
    del visibility, owner_user_id
    if not is_safe_slug(slug):
        return {"status": "not_found", "progress": 0, "total": 0}

    suite_key = next((k for k in _all_suite_keys() if f"_{k}_" in f"_{slug}_"), None)
    total = suite_question_count(suite_key) if suite_key else 0

    path = RESULTS_DIR / f"{slug}.jsonl"
    progress = 0
    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            progress = sum(1 for line in f if line.strip())

    if total and progress >= total:
        return {
            "status": "complete",
            "progress": progress,
            "total": total,
            "message": "",
            "log_path": f"evaluator/results/{slug}.log",
        }

    log_path = RESULTS_DIR / f"{slug}.log"
    rel_log = f"evaluator/results/{slug}.log"

    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return {
            "status": "running",
            "progress": progress,
            "total": total,
            "log_path": rel_log,
            **run_log_payload(log_path),
        }
    if proc is not None:  # exited without a complete file
        return {
            "status": "failed",
            "progress": progress,
            "total": total,
            "message": status_message(log_path, failed=True),
            "log_path": rel_log,
        }
    if path.is_file():
        # partial file, no registered process (e.g. Flask restarted mid-run)
        return {
            "status": "failed",
            "progress": progress,
            "total": total,
            "message": status_message(log_path, failed=True),
            "log_path": rel_log,
        }
    return {"status": "not_found", "progress": 0, "total": 0, "message": ""}


def is_eval_run_in_progress(slug: str) -> bool:
    """True when a registered subprocess for *slug* is still running."""
    if not is_safe_slug(slug):
        return False
    proc = _RUNNING.get(slug)
    if proc is not None and proc.poll() is None:
        return True
    return get_status(slug)["status"] == "running"


def validate_custom_questions(
    raw_text: str,
) -> tuple[list[dict] | None, str | None]:
    """Parse + validate pasted custom questions. Returns (questions, None) or
    (None, error_message).

    Format: one JSON object per line, each with a non-empty ``question`` and
    ``reference`` (the user's own gold answer); optional ``id``. This is the
    security boundary for custom content — it's parsed as DATA, capped, and
    only ever becomes prompt text the candidate sees; it never reaches a shell
    or the filesystem as a path.
    """
    lines = [ln for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return None, "no questions provided"
    if len(lines) > CUSTOM_MAX_QUESTIONS:
        return None, f"too many questions ({len(lines)}); max {CUSTOM_MAX_QUESTIONS}"

    questions: list[dict] = []
    for i, line in enumerate(lines, start=1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            return None, f"line {i} is not valid JSON: {e}"
        if not isinstance(obj, dict):
            return None, f"line {i} must be a JSON object"
        question = str(obj.get("question", "")).strip()
        reference = str(obj.get("reference", "")).strip()
        if not question:
            return None, f"line {i} is missing a non-empty 'question'"
        if not reference:
            return None, f"line {i} is missing a non-empty 'reference'"
        if len(question) > CUSTOM_MAX_FIELD_CHARS or len(reference) > CUSTOM_MAX_FIELD_CHARS:
            return None, f"line {i} exceeds {CUSTOM_MAX_FIELD_CHARS} chars per field"
        qid = str(obj.get("id", "")).strip() or f"custom-{i:03d}"
        questions.append({"id": qid, "question": question, "reference": reference})
    return questions, None


def write_custom_suite(questions: list[dict]) -> str:
    """Write a one-off custom suite file and return its suite_key.

    The key is ``custom_<ts>``; the metadata line marks it ad-hoc so the
    comparison table can keep it out of locked-suite comparisons.
    """
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    suite_key = f"{CUSTOM_PREFIX}{ts}"
    CUSTOM_SUITES_DIR.mkdir(parents=True, exist_ok=True)
    path = CUSTOM_SUITES_DIR / f"{suite_key}.jsonl"
    metadata = {
        "_metadata": (
            "User-provided custom suite — ad-hoc, NOT a locked comparable "
            "suite. References are the user's own. Excluded from the main "
            "model-comparison table."
        ),
        "task_suite_version": suite_key,
        "custom": True,
    }
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        for q in questions:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    return suite_key


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
        "suggested_hf_repos": list(SUGGESTED_HF_REPOS),
        "custom_max_questions": CUSTOM_MAX_QUESTIONS,
        "launch_mode": "docker" if docker_launch.use_docker() else "host",
        "docker_available": docker_launch.docker_available(),
    }
