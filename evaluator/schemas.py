"""
schemas.py
==========

Canonical contract for the evaluation pipeline. Every result row written by
the runner conforms to EvaluationResult. The same schema is what the
nutrition-label dashboard will consume, and what the security pair should
match against when their scanner produces companion rows for the same model.

Design lineage:
  - HELM (scenario + adaptation + metric) — adaptation metadata is a first-class
    field, not an afterthought.
  - G-Eval — per-dimension scores with rationales, never a single vague number.
  - Stakeholder synthesis — operational metrics (latency, tokens, cost) are
    separate from response-quality scores; they are logged, not judged.

Do NOT add new top-level fields without updating the version field below and
notifying the security pair + dashboard track. Schema churn is the structural
risk this week.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Optional


# Bump this when the result-row contract changes. Downstream consumers can
# refuse rows whose schema_version they don't recognize.
SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Per-dimension score (G-Eval style)
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """One rubric dimension scored by the judge.

    `score` is on the scale defined by the rubric for that dimension
    (e.g. 1-5 for accuracy, 1-3 for tone). The rubric YAML is the source
    of truth for what each scale means; this struct just carries the number
    and the judge's one-line rationale so a human can sanity-check it.
    """
    score: float
    rationale: str


# ---------------------------------------------------------------------------
# Adaptation metadata (HELM lesson: log everything that could move the score)
# ---------------------------------------------------------------------------

@dataclass
class Adaptation:
    """Everything about HOW the model was prompted and how it was judged.

    If any of these change, the result row is from a different experiment.
    Versions are strings (e.g. 'it_support_v1') not git SHAs, to keep them
    human-readable in the dashboard. Map version-string -> file in the repo.
    """
    candidate_model: str
    candidate_model_version: str            # e.g. 'Gateway 2026-05'
    system_prompt_version: str              # filename of system prompt template
    user_prompt_template_version: str
    temperature: float
    max_tokens: int
    task_suite_version: str
    rubric_version: str
    judge_model: str
    judge_prompt_version: str


# ---------------------------------------------------------------------------
# Operational metrics (logged, not judged)
# ---------------------------------------------------------------------------

@dataclass
class Operational:
    """Cost / speed / reliability. Faber cares about these for Gateway
    deployment decisions. Keep them separate from quality scores: the judge
    does not see these and they don't go into the rubric.
    """
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float


# ---------------------------------------------------------------------------
# The result row
# ---------------------------------------------------------------------------

@dataclass
class EvaluationResult:
    """One row = (one question) x (one candidate model) x (one judge run).

    Written one-per-line to results/<timestamp>_<suite>_<model>.jsonl so a
    crashed run loses at most the in-flight question.
    """
    # identity
    evaluation_run_id: str          # uuid4, shared by all rows from one run
    timestamp: str                  # ISO 8601, UTC
    question_id: str
    suite: str                      # e.g. 'it_support'
    schema_version: str

    # how the model was used
    adaptation: Adaptation

    # what the model said
    candidate_response: str

    # how it scored (G-Eval per-dimension; rubric YAML defines which dims exist)
    scores: dict[str, DimensionScore]
    overall: Optional[float]        # weighted aggregate; None if any dim failed

    # how the call performed
    operational: Operational

    # failure handling — never crash a run, always write a row
    candidate_failed: bool = False
    judge_failed: bool = False
    error: Optional[str] = None

    # ---- serialization helpers ----

    def to_dict(self) -> dict:
        """JSON-serializable dict. Use this, not asdict(), so dataclass
        nesting flattens cleanly."""
        d = asdict(self)
        # asdict already recurses; nothing custom needed yet, but this is
        # the seam to convert e.g. Decimal cost or numpy floats later.
        return d

    def to_jsonl(self) -> str:
        """One JSONL line (no trailing newline; the writer adds it)."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "EvaluationResult":
        """Round-trip for reading a result file back."""
        d = dict(d)  # don't mutate caller's dict
        d["adaptation"] = Adaptation(**d["adaptation"])
        d["operational"] = Operational(**d["operational"])
        d["scores"] = {k: DimensionScore(**v) for k, v in d["scores"].items()}
        return cls(**d)


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

def new_run_id() -> str:
    """Stable UUID for grouping all rows from one evaluation run."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """UTC ISO-8601 timestamp, second precision."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---------------------------------------------------------------------------
# Self-test: round-trip a representative row
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample = EvaluationResult(
        evaluation_run_id=new_run_id(),
        timestamp=now_iso(),
        question_id="it-support-007",
        suite="it_support",
        schema_version=SCHEMA_VERSION,
        adaptation=Adaptation(
            candidate_model="meta-llama/Llama-3.1-8B-Instruct",
            candidate_model_version="Gateway 2026-05",
            system_prompt_version="it_support_v1",
            user_prompt_template_version="it_support_v1",
            temperature=0.2,
            max_tokens=500,
            task_suite_version="it_support_v1",
            rubric_version="it_support_v1",
            judge_model="gpt-5",
            judge_prompt_version="reference_based_v1",
        ),
        candidate_response="Go to oit.duke.edu/netid and follow the prompts...",
        scores={
            "accuracy":         DimensionScore(score=4, rationale="Correct URL and flow; missing Duo step."),
            "completeness":     DimensionScore(score=3, rationale="Lacks troubleshooting if Duo isn't set up."),
            "policy_adherence": DimensionScore(score=5, rationale="No policy-violating advice."),
            "tone":             DimensionScore(score=3, rationale="Clear and professional."),
        },
        overall=3.8,
        operational=Operational(
            latency_ms=1840,
            prompt_tokens=312,
            completion_tokens=187,
            estimated_cost_usd=0.0021,
        ),
    )

    # Round-trip check
    line = sample.to_jsonl()
    parsed = EvaluationResult.from_dict(json.loads(line))
    assert parsed.scores["accuracy"].score == 4
    assert parsed.adaptation.judge_model == "gpt-5"
    assert parsed.operational.latency_ms == 1840
    print("schemas.py self-test passed.")
    print(json.dumps(parsed.to_dict(), indent=2, ensure_ascii=False))
