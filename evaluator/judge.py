"""
judge.py

LLM-as-judge using a G-Eval style reference-based template. One public
function: ``judge_response``. Scores a single (question, reference,
candidate_response) tuple against the locked rubric and returns four
per-dimension scores with rationales.

Methodology lineage:
  - G-Eval (Liu et al. 2023): structured template, anchored scale, CoT
    via evaluation_steps in the rubric YAML.
  - MT-Bench / Zheng et al.: judge temperature = 0, judge must come from
    a different model family than the candidates being evaluated.
  - HELM: per-dimension scores remain visible; no collapse to one number.

Used by the runner (Wednesday) right after generate_candidate. Never
raises on judge failure: on bad JSON or API error, returns a JudgeResult
with failed=True and the error string so the runner can write a failure
row and keep going.

File cache:
    ``evaluator/cache/judges/<sha256>.json``  keyed on
    ``(judge_model, judge_prompt_version, question, candidate_response,
       rubric_version)``. Re-runs return the cached row without calling
    the API. Failed judgments are NOT cached (transient errors retry).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from _gateway import gateway_client
from schemas import DimensionScore


_CACHE_DIR = Path(__file__).parent / "cache" / "judges"

# The four dimension keys the judge must return, in the order they appear in
# the rubric and prompt. The runner relies on this set to validate parsed JSON.
_EXPECTED_DIMENSIONS = ("accuracy", "completeness", "policy_adherence", "tone")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class JudgeResult:
    """What ``judge_response`` returns. ``scores`` keys are the rubric
    dimension names (accuracy, completeness, policy_adherence, tone); each
    value is a ``DimensionScore`` reused from schemas.py so result-row
    construction in the runner has no copy hoops.
    """

    scores: dict[str, DimensionScore] = field(default_factory=dict)
    failed: bool = False
    error: Optional[str] = None
    raw_response: str = ""  # for debugging when parsing fails


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(
    *,
    judge_model: str,
    judge_prompt_version: str,
    question: str,
    candidate_response: str,
    rubric_version: str,
) -> str:
    raw = (
        f"{judge_model}|{judge_prompt_version}|{question}"
        f"|{candidate_response}|{rubric_version}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def _cache_read(key: str) -> Optional[JudgeResult]:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data["scores"] = {k: DimensionScore(**v) for k, v in data["scores"].items()}
        return JudgeResult(**data)
    except (json.JSONDecodeError, OSError, TypeError, KeyError) as e:
        # A truncated (killed mid-write) or stale-shape entry must read as a
        # cache miss, not crash the run. Drop it; the fresh API call rewrites it.
        print(
            f"  WARN: discarding corrupt judge cache entry {path.name}: {e}",
            file=sys.stderr,
        )
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _cache_write(key: str, result: JudgeResult) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "scores": {k: asdict(v) for k, v in result.scores.items()},
        "failed": result.failed,
        "error": result.error,
        "raw_response": result.raw_response,
    }
    target = _cache_path(key)
    # Write-then-rename so a killed run never leaves a half-written entry.
    # The pid suffix keeps concurrent runs from sharing a temp file; the
    # rename itself is atomic on POSIX.
    tmp = target.with_name(f"{key}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(target)


# ---------------------------------------------------------------------------
# JSON parsing — strict, with one tolerant fallback
# ---------------------------------------------------------------------------


def _strip_fences(text: str) -> str:
    """Remove ``` or ```json fences if the judge added them despite instructions."""
    fence_pat = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
    return fence_pat.sub("", text).strip()


def _parse_scores(
    raw: str,
    expected_dims: tuple[str, ...] = _EXPECTED_DIMENSIONS,
) -> dict[str, DimensionScore]:
    """Parse a JSON judge response into a {dim: DimensionScore} dict.

    ``expected_dims`` lets the caller pin which dimension keys must appear
    in the JSON. Defaults to the original IT-support set for backward
    compatibility; the runner now passes the actual rubric's dimension
    list (derived from the resolved rubric).

    Raises ValueError with a specific message on any structural issue so the
    retry path can include it in the follow-up message to the judge.
    """
    text = _strip_fences(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"response was not valid JSON: {e}") from e

    if not isinstance(obj, dict):
        raise ValueError("response JSON must be an object, got a different type")

    missing = [d for d in expected_dims if d not in obj]
    if missing:
        raise ValueError(f"missing required dimension(s): {missing}")

    extra = [k for k in obj if k not in expected_dims]
    if extra:
        raise ValueError(f"unexpected key(s) in response: {extra}")

    scores: dict[str, DimensionScore] = {}
    for dim in expected_dims:
        entry = obj[dim]
        if not isinstance(entry, dict):
            raise ValueError(f"dimension '{dim}' must be an object")
        if "score" not in entry or "rationale" not in entry:
            raise ValueError(f"dimension '{dim}' must have 'score' and 'rationale'")
        try:
            score = float(entry["score"])
        except (TypeError, ValueError) as e:
            raise ValueError(f"dimension '{dim}' score is not numeric") from e
        rationale = str(entry["rationale"]).strip()
        scores[dim] = DimensionScore(score=score, rationale=rationale)

    return scores


# ---------------------------------------------------------------------------
# Rubric loader — resolves {from: shared} references against the shared lib
# ---------------------------------------------------------------------------


def resolve_rubric(rubric_path: Path) -> tuple[dict, str]:
    """Load a rubric YAML and inline any shared-dimension references.

    A rubric can reference reusable dimensions defined in a sibling shared
    library file (``_shared_dimensions.yaml``). When a dimension body has
    ``from: shared``, this resolver copies the ``definition`` / ``scale`` /
    ``anchors`` from the shared library and layers the per-task ``weight``
    and ``task_note`` over them.

    Returns a tuple of (resolved_rubric_dict, resolved_yaml_text). The
    YAML text is what gets inlined into the judge prompt template; the
    dict is what the runner reads ``rubric_version`` / ``aggregation`` /
    etc. from.

    Backward-compatible: rubrics without a ``shared_dimensions_lib`` key
    (e.g. the locked ``it_support_v1.yaml``) pass through unchanged — the
    original YAML text is returned as-is so this refactor is a no-op for
    inline rubrics.
    """
    raw = rubric_path.read_text(encoding="utf-8")
    rubric = yaml.safe_load(raw)

    shared_lib_name = rubric.get("shared_dimensions_lib")
    if not shared_lib_name:
        # Pure inline rubric — return as-is.
        return rubric, raw

    shared_lib_path = rubric_path.parent / shared_lib_name
    if not shared_lib_path.is_file():
        raise FileNotFoundError(
            f"Rubric {rubric_path.name!r} references shared library "
            f"{shared_lib_name!r} but it was not found at {shared_lib_path}"
        )
    shared = yaml.safe_load(shared_lib_path.read_text(encoding="utf-8"))
    shared_dims = (shared or {}).get("dimensions") or {}

    resolved_dims: dict[str, dict] = {}
    for dim_name, dim_body in (rubric.get("dimensions") or {}).items():
        if isinstance(dim_body, dict) and dim_body.get("from") == "shared":
            if dim_name not in shared_dims:
                raise KeyError(
                    f"Dimension {dim_name!r} in {rubric_path.name} is marked "
                    f"from:shared but is not defined in {shared_lib_name}"
                )
            # Start from the shared definition; overlay rubric's task fields.
            merged = dict(shared_dims[dim_name])
            for key, val in dim_body.items():
                if key == "from":
                    continue
                merged[key] = val
            resolved_dims[dim_name] = merged
        else:
            # Inline dimension — keep verbatim.
            resolved_dims[dim_name] = dim_body

    # Build the resolved rubric dict. Drop shared-lib metadata once
    # resolution is done so the judge prompt isn't littered with it.
    resolved = dict(rubric)
    resolved["dimensions"] = resolved_dims
    resolved.pop("shared_dimensions_lib", None)
    resolved.pop("shared_dimensions_version", None)

    resolved_yaml = yaml.safe_dump(
        resolved,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=4096,
    )
    return resolved, resolved_yaml


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def judge_response(
    *,
    question: str,
    reference: str,
    candidate_response: str,
    rubric_path: Path,
    judge_model: str,
    judge_prompt_path: Path,
    timeout_sec: float = 30.0,
    max_tokens: int = 600,
) -> JudgeResult:
    """Score a candidate response against a reference using an LLM judge.

    Loads the rubric YAML and judge prompt template, formats them with the
    inputs, calls the Gateway at temperature 0 (MT-Bench rule), and parses
    the response as strict JSON. On parse failure, retries ONCE with a
    follow-up message instructing the judge to return only valid JSON.
    If the second attempt also fails, returns ``JudgeResult(failed=True)``
    with the parse error and raw response for debugging.

    Successful judgments are cached under evaluator/cache/judges/, keyed on
    (judge_model, judge_prompt_version, question, candidate_response,
     rubric_version). Cache hit returns the saved scores without any API call.
    """
    # ----- load contracts (rubric + template version come from these files) -----
    # resolve_rubric returns the rubric YAML with any {from: shared} references
    # inlined against _shared_dimensions.yaml. For inline rubrics like the locked
    # it_support_v1.yaml this is a no-op (original YAML returned unchanged).
    rubric, rubric_raw = resolve_rubric(rubric_path)
    rubric_version: str = str(rubric.get("rubric_version", rubric_path.stem))

    template = judge_prompt_path.read_text(encoding="utf-8")
    judge_prompt_version = judge_prompt_path.stem  # e.g. 'reference_based_v1'

    # ----- cache lookup -----
    key = _cache_key(
        judge_model=judge_model,
        judge_prompt_version=judge_prompt_version,
        question=question,
        candidate_response=candidate_response,
        rubric_version=rubric_version,
    )
    cached = _cache_read(key)
    if cached is not None:
        return cached

    # ----- derive rubric-specific output schema -----
    # The dimension keys the judge must produce. For backward compat with
    # the hardcoded reference_based_v1.txt template, _EXPECTED_DIMENSIONS
    # still works; v2 template uses these to build {output_schema}.
    expected_dims: tuple[str, ...] = tuple((rubric.get("dimensions") or {}).keys())
    if not expected_dims:
        expected_dims = _EXPECTED_DIMENSIONS

    output_schema_lines = ["{"]
    max_dim_len = max(len(d) for d in expected_dims)
    for i, dim in enumerate(expected_dims):
        scale = (rubric.get("dimensions") or {}).get(dim, {}).get("scale", [1, 5])
        comma = "," if i < len(expected_dims) - 1 else ""
        pad = " " * (max_dim_len - len(dim) + 2)
        output_schema_lines.append(
            f'  "{dim}":{pad}{{"score": <int {scale[0]}-{scale[1]}>, '
            f'"rationale": "<one sentence>"}}{comma}'
        )
    output_schema_lines.append("}")
    output_schema = "\n".join(output_schema_lines)

    # ----- format the user message -----
    # Extra kwargs (like output_schema) are silently ignored by templates
    # that don't reference them — so this is backward-compatible with
    # the hardcoded reference_based_v1.txt template.
    user_message = template.format(
        question=question,
        reference=reference,
        candidate=candidate_response,
        rubric_yaml=rubric_raw,
        output_schema=output_schema,
    )

    client = gateway_client().with_options(timeout=timeout_sec)
    messages: list[dict] = [{"role": "user", "content": user_message}]

    # ----- attempt 1 -----
    try:
        resp = client.chat.completions.create(
            model=judge_model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
        )
        raw1 = (resp.choices[0].message.content or "").strip()
    except Exception as e:  # never crash; record and continue
        return JudgeResult(
            failed=True,
            error=f"{type(e).__name__}: {e}",
            raw_response="",
        )

    try:
        scores = _parse_scores(raw1, expected_dims=expected_dims)
        result = JudgeResult(scores=scores, raw_response=raw1)
        _cache_write(key, result)
        return result
    except ValueError as parse_err_1:
        first_error = str(parse_err_1)

    # ----- attempt 2 (follow-up message asking for valid JSON only) -----
    messages.extend(
        [
            {"role": "assistant", "content": raw1},
            {
                "role": "user",
                "content": (
                    "Your previous response failed JSON parsing: "
                    f"{first_error}. Reply with ONLY the JSON object specified "
                    "in the OUTPUT FORMAT section — no prose, no code fences, "
                    "no leading or trailing text. Use these exact dimension "
                    f"keys: {', '.join(expected_dims)}."
                ),
            },
        ]
    )
    try:
        resp2 = client.chat.completions.create(
            model=judge_model,
            messages=messages,
            temperature=0,
            max_tokens=max_tokens,
        )
        raw2 = (resp2.choices[0].message.content or "").strip()
    except Exception as e:
        return JudgeResult(
            failed=True,
            error=f"retry API error: {type(e).__name__}: {e}",
            raw_response=raw1,
        )

    try:
        scores = _parse_scores(raw2, expected_dims=expected_dims)
        result = JudgeResult(scores=scores, raw_response=raw2)
        _cache_write(key, result)
        return result
    except ValueError as parse_err_2:
        return JudgeResult(
            failed=True,
            error=(
                f"JSON parse failed twice. first: {first_error}. "
                f"second: {parse_err_2}."
            ),
            raw_response=raw2,
        )


# ---------------------------------------------------------------------------
# Smoke test — deliverable: real judge scores from the Gateway.
# Run:  cd evaluator && python judge.py
# Requires DUKE_GATEWAY_URL and DUKE_GATEWAY_KEY in .env.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    from candidate import generate_candidate

    here = Path(__file__).parent
    rubric_path = here / "tasks" / "rubrics" / "it_support.yaml"
    judge_prompt_path = here / "prompts" / "judge" / "reference_based_v1.txt"
    system_prompt_path = here / "prompts" / "system" / "it_support_v1.txt"
    suite_path = here / "tasks" / "it_support_v1.jsonl"

    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    # Pull question 1 (and its gold reference) out of the locked suite.
    with suite_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()
    # Line 0 is metadata; line 1 is question 1.
    row = json.loads(lines[1])
    question = row["question"]
    reference = row["reference"]

    candidate_model = "gpt-5-chat"
    # MT-Bench rule: judge ≠ candidate family AND judge >= candidate capability.
    # Llama 4 Maverick is the strongest different-family judge on Duke's allowlist
    # for a GPT-5 candidate. See compare_judges.py for the Llama 3.3 vs Maverick
    # delta experiment that justified picking Maverick over 3.3.
    judge_model = "Llama 4 Maverick"

    print(f"Candidate: {candidate_model}  |  Judge: {judge_model}")
    print(f"Question:  {question}")
    print()

    cand = generate_candidate(
        question=question,
        model=candidate_model,
        system_prompt=system_prompt,
    )
    if cand.failed:
        print(f"CANDIDATE FAILED: {cand.error}")
        raise SystemExit(1)

    print("=== Candidate response (truncated) ===")
    print(cand.response[:500] + ("..." if len(cand.response) > 500 else ""))
    print()

    verdict = judge_response(
        question=question,
        reference=reference,
        candidate_response=cand.response,
        rubric_path=rubric_path,
        judge_model=judge_model,
        judge_prompt_path=judge_prompt_path,
    )

    print("=== JudgeResult ===")
    print(f"failed:  {verdict.failed}")
    if verdict.failed:
        print(f"error:   {verdict.error}")
        print(f"raw:     {verdict.raw_response[:300]}")
        raise SystemExit(1)

    for dim, ds in verdict.scores.items():
        print(f"  {dim:18s}  score={ds.score:>4}   {ds.rationale}")
