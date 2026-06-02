# Week 3 build task — day-by-day

Read `CLAUDE.md` first. Then read the four contract files:
- `schemas.py`
- `metrics.yaml`
- `tasks/rubrics/it_support.yaml`
- `tasks/it_support_v1.jsonl`

These are locked. Do not modify them. Build against them.

## How this week works

We build one chunk per day, Monday through Friday. You stop at the end of each day's chunk and **wait for me to come back the next day** before starting the next one. I need to report daily progress to my mentor, so each day's work has to be something I can explain on my own.

Pace target per day: a focused, well-scoped chunk a person could write and understand in a working day. Not a single function — a real piece of the pipeline. Not the whole pipeline either.

## What I expect from you each day

For every day:

1. **Before writing any code**, post a short plan (3-5 bullets) for what you're about to build that day, and wait for me to confirm. This lets me catch any misunderstanding before tokens get spent.

2. Write the code for that day, and only that day. Do not start tomorrow's work even if you finish early. If you have spare cycles, improve test coverage or comments on today's work.

3. **After the code is done**, post a short explanation:
   - What was built (one sentence per file or function)
   - The 2-3 design decisions worth knowing about (why you chose X over Y)
   - Anything that's deliberately incomplete or rough — explicitly flagged
   - What questions I should be ready to answer if my mentor asks "why is it this way?"

4. **Then stop.** Do not continue to the next day's work. Wait for me to come back.

If a day's spec is unclear, ask a clarifying question before coding. Don't guess.

## The week plan (read all of this so you know where we're going, then build one day at a time)

### Monday — Gateway client

Build `candidate.py`: a thin wrapper around the OpenAI SDK pointed at the Duke AI Gateway.

Read base URL and key from env vars `DUKE_GATEWAY_URL` and `DUKE_GATEWAY_KEY`. Fail fast with a clear error if either is missing.

One function:
```python
def generate_candidate(
    *,
    question: str,
    model: str,
    system_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 500,
    timeout_sec: float = 30.0,
) -> CandidateResult
```

`CandidateResult` is a small dataclass: `response: str`, `latency_ms: int`, `prompt_tokens: int`, `completion_tokens: int`, `failed: bool`, `error: Optional[str]`.

Behavior: measure `latency_ms` as wall-clock from request send to response received. Pull token counts from the API response usage field. On timeout or API error, return `failed=True` with the error string — do not raise.

Add a basic file cache: hash of (model, system_prompt, question, temperature) → cached response under `cache/candidates/`. A re-run with the same inputs reads from cache instead of calling the API.

Also write the `prompts/system/it_support_v1.txt` file Monday since `candidate.py` won't be testable without it. ~100 words. Frame the model as a helpful Duke OIT support assistant. Concise, Duke-specific (URLs, phone numbers), flag policy concerns where relevant, recommend OIT Service Desk (919-684-2200) for escalation.

End of Monday: I should be able to run `python -c "from candidate import generate_candidate; ..."` and get a real response back from the Gateway on one test question.

### Tuesday — Judge prompt + judge module

Tuesday is two things: the judge prompt template (a text file) and the `judge.py` module that uses it.

First, write `prompts/judge/reference_based_v1.txt` — a G-Eval style template with these `{name}` variables for Python `str.format`:
- `{question}` — the user question
- `{reference}` — gold reference answer
- `{candidate}` — candidate model's response
- `{rubric_yaml}` — the entire rubric YAML inlined so dimensions and anchors are visible

The judge must respond with valid JSON, no markdown fences, no prose outside the JSON, using these exact dimension keys:
```json
{
  "accuracy":         {"score": <int>, "rationale": "<one sentence>"},
  "completeness":     {"score": <int>, "rationale": "<one sentence>"},
  "policy_adherence": {"score": <int>, "rationale": "<one sentence>"},
  "tone":             {"score": <int>, "rationale": "<one sentence>"}
}
```

The template should walk the judge through the `evaluation_steps` in the rubric YAML. Read that file to see the steps.

Then write `judge.py`:

```python
def judge_response(
    *,
    question: str,
    reference: str,
    candidate_response: str,
    rubric_path: Path,
    judge_model: str,
    judge_prompt_path: Path,
) -> JudgeResult
```

`JudgeResult` dataclass: `scores: dict[str, DimensionScore]`, `failed: bool`, `error: Optional[str]`. Reuse `DimensionScore` from `schemas.py`.

Steps the function takes:
1. Load the rubric YAML and judge prompt template
2. Format the template with the inputs and the inlined rubric YAML
3. Call the judge via the Gateway at temperature 0
4. Parse the response as JSON. If parsing fails, retry once with a follow-up message instructing it to return only valid JSON. If second attempt also fails, return `failed=True` with the raw response as the error.
5. Map parsed JSON into `dict[str, DimensionScore]`

Cache judge responses under `cache/judges/` keyed on hash of (judge_model, judge_prompt_version, question, candidate_response, rubric_version).

End of Tuesday: I should be able to feed one (question, reference, candidate response) tuple to `judge_response` and get back a `JudgeResult` with four dimension scores.

### Wednesday — Runner

Build `runner.py`. This is the orchestration that ties Monday's and Tuesday's work together.

CLI:
```bash
python runner.py --suite tasks/it_support_v1.jsonl \
                 --rubric tasks/rubrics/it_support.yaml \
                 --candidate-model <model-id> \
                 --judge-model <judge-id> \
                 --system-prompt prompts/system/it_support_v1.txt \
                 --judge-prompt prompts/judge/reference_based_v1.txt
```

For each question in the suite (skip the metadata line):
1. Call `generate_candidate(...)`
2. Call `judge_response(...)`
3. Compute the weighted overall using the rubric's aggregation block (normalize each score to its scale max, then weight; the rubric has the formula)
4. Construct an `EvaluationResult` row with all adaptation metadata and operational metrics filled in
5. Append the row as one JSON line to `results/<timestamp>_<suite>_<candidate>.jsonl`
6. Print one progress line per question to stdout

The runner never crashes on individual question failures. If `candidate_failed=True`, skip the judge step and write the row with the failure flag. Same for `judge_failed=True`.

End of Wednesday: I should be able to run the CLI against the 12-question suite and get a results JSONL with 12 rows back. Each row should conform to the `EvaluationResult` schema.

### Thursday — Aggregator + first real run

Build `aggregate.py`. Read a results JSONL file, compute per-dimension mean scores, the overall mean, mean latency, total cost, and failure rate. Print a small text-aligned table to stdout. No fancy formatting — `print()` is fine.

Then run the full pipeline (runner + aggregator) on one candidate model. Look at the output. Sanity-check that scores aren't all 5s, operational metrics are recorded, and nothing is suspicious.

End of Thursday: I have the first real numbers from this pipeline, and I know what they say.

### Friday — Second model + small README

Run the pipeline on a *second* candidate model. Compare. This is the day we see whether the pipeline actually discriminates between models.

Then write a short README in the directory documenting how to run a scan: env vars to set, the CLI command, where outputs land, what to expect. Half a page, not formal docs.

End of Friday: the eval pipeline runs on multiple models, produces real numbers, and there's a README a teammate could read to run it themselves.

## What to do on Day 1 (Monday) right now

1. Read CLAUDE.md and the four contract files.
2. Post a 3-5 bullet plan for Monday's work specifically.
3. Wait for me to confirm before writing code.

Do NOT plan Tuesday-Friday. We'll handle those one at a time.

## What to ask me about on Monday before coding

- The exact Gateway base URL
- The exact model identifier strings on the Gateway (e.g., is it `meta-llama/Llama-3.1-8B-Instruct` or some other format?)
- Whether the Gateway uses standard OpenAI-style Bearer auth or something else

I'll set `DUKE_GATEWAY_KEY` as an env var; don't ask me to paste the key into chat.

## Definition of done — for the week, not the day

By end of Friday: a runnable `python runner.py` evaluates a candidate model on the 12-question IT support suite through the Duke AI Gateway, produces a JSONL of `EvaluationResult` rows, and `python aggregate.py` prints a summary table. Pipeline tested on at least two models. README exists. No changes to any contract file.

Daily checkpoints along the way (Monday's chunk done by Monday EOD, etc.) — not catching up all on Friday.
