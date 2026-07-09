# Model Pipeline Gating — Design

**Date:** 2026-07-09
**Author:** evaluator pillar
**Status:** Approved for planning

## Goal

When a user submits a job / chooses a model, the model must pass the earlier
pillars before it can be evaluated or benchmarked:

- **Security scanning** (scanner pillar), then
- **Safety / red-teaming** (safety pillar), then
- **Eval + benchmarks** unlock.

Enforcement is a **hard block**: the eval/benchmark launch is refused
server-side until the prerequisite gate(s) are cleared. This mirrors the
existing scanner gate, which is a `TASK.md` hard constraint (no unvalidated
value reaches a subprocess).

## Source-aware gates (key constraint)

The two pillars cover **different model populations**, so the sequence is not
one uniform chain:

| Source | Scan | Safety | Then |
|---|---|---|---|
| **Gateway** (e.g. `Llama 4 Maverick`) | N/A — an API endpoint has no repo files to scan | ✅ probes the live endpoint via the gateway | eval + benchmark |
| **HF repo** (e.g. `Qwen/Qwen2.5-7B-Instruct`) | ✅ scans repo files (pickle, deps, secrets) | ❌ **not executable today** — the model isn't on the gateway, and `safety_launch.validate_launch` only accepts eligible gateway models | eval (existing scan→eval gate) |

**HF-safety gap.** Making an HF model safety-testable means serving it on the
DCC and pointing the safety pillar at that ephemeral endpoint — substantial
work inside the safety pillar + DCC orchestrator (teammates' code). Out of
scope for this change. The `/pipeline` page surfaces it explicitly as
"safety red-teaming not yet supported for served HF models (coordinate with
safety pillar)" — never silently skipped.

## Decisions (locked)

- **Scope:** full unified pipeline/wizard, source-aware gates.
- **Enforcement:** hard block (no override).
- **Safety "cleared" bar:** completed run with `composite_tier == "low"` —
  mirrors the scanner gate exactly (`status` complete + `severity_tier` low).
- **Chaining:** enforce prerequisites only. The user kicks off each stage; no
  background auto-chaining orchestrator (respects the no-queue/no-Celery
  constraint in `CLAUDE.md`).
- **State model:** derive stage state from the existing scanner + safety
  artifacts. **No new registry/DB** — the artifacts already answer "did this
  clear?"; a second source of truth would only drift.

## Ownership & boundaries

Per the team split, the evaluator pillar is owned here. The scanner/safety
pillar code and the shared benchmark launch are owned by other pillars:

| File | Owner | This change |
|---|---|---|
| `frontend/eval_launch.py` | evaluator | Edit — add gateway safety gate |
| `frontend/pipeline.py` | evaluator (new) | New — gate logic + stage state |
| `frontend/pipeline_routes.py` | evaluator (new) | New — `/pipeline` route |
| `frontend/templates/pipeline.html` | evaluator (new) | New — unified view |
| `frontend/__init__.py` | shared | Edit — one additive registration line |
| `frontend/routes.py` | shared (evaluator owns eval routes) | Edit — gate call in eval route |
| `frontend/benchmark_launch.py` / benchmark route | benchmark pillar | **Out of this implementation** — evaluator owner wires the benchmark guard separately |
| `scanner/`, `safety/`, `scan_launch.py`, `safety_launch.py` | scanner + safety pillars | **Read-only** — consumed, never edited |

The benchmark hard-block is handled separately by the evaluator owner and is
**not part of this implementation**. This implementation only guarantees the
reusable `require_ready_for_downstream` gate exists and is benchmark-ready; the
owner inserts the call into the benchmark route when coordinating with the
benchmark pillar.

## Components

### 1. `frontend/pipeline.py` (new) — single source of truth for gates

Reuses the existing artifact-reading handshake pattern
(`eval_launch.validate_hf_scan_gate`, which reads
`scanner.paths.output_dir(repo_id)/scan_result.json`).

```
CLEARED_TIER = "low"
COMPLETE_STATUSES = {"complete", "completed"}

def validate_safety_gate(model, *, profile="base") -> dict:
    # Reads safety/output/<slug>/<profile>/merged_safety_result.json via
    # safety.merged_paths.merged_result_path + safety.gateway_ids.normalize_gateway_model_id
    # cleared iff status in COMPLETE_STATUSES and composite_tier == CLEARED_TIER
    # returns {ok, error, status, tier, ...}

def stage_state(model, source) -> dict:
    # source in {"gateway", "hf"}
    # returns {"scan": <gate>, "safety": <gate>, "eval_unlocked": bool}
    # each <gate> in: n/a | missing | running | cleared | blocked | unsupported
    # gateway: scan=n/a, safety=<validate_safety_gate>
    # hf:      scan=<validate_hf_scan_gate>, safety=unsupported

def require_ready_for_downstream(model, source) -> str | None:
    # hard-block check reused by eval + benchmark
    # gateway: safety must be cleared
    # hf:      scan must be cleared (safety unsupported → not required)
```

- Gate "running" is read from the pillars' existing status helpers
  (`safety_launch.get_status`, `scan_launch.get_status`) — read-only.
- The scanner-gate half delegates to / shares logic with the existing
  `validate_hf_scan_gate` so there is exactly one definition of "scan cleared".

### 2. Gate enforcement

- **Eval (gateway path):** `eval_launch.py` gains a safety-gate check; the
  eval route (`routes.py::eval_run_start` / `eval_run_start_custom`, gateway
  branch) calls it before `start_run`. Today the gateway path has **no** gate.
  The HF branch keeps its existing scan gate.
- **Eval (HF path):** unchanged — existing scan gate stands; safety is
  `unsupported` and therefore not required.
- **Benchmark:** the same guard belongs in `benchmark_run_start`
  (`err = pipeline.require_ready_for_downstream(model, source); if err: return err, 400`),
  but is wired separately by the evaluator owner — **not implemented here**.
  This spec only guarantees the gate function exists and is benchmark-ready.

### 3. `/pipeline` page (new)

- Lists gateway models (from `gateway.catalog`) and any HF repos that already
  have a scan artifact (enumerated read-only via `scan_data.get_scans_data`).
- Per model: stage badges (scan / safety / eval) driven by `stage_state`, plus
  "Run scan" / "Run safety" links to the existing `/scans/new` and
  `/safety/new` forms. Eval/benchmark buttons are enabled only when
  `eval_unlocked`.
- HF rows show the safety-unsupported note.
- Registered via `register_pipeline_routes(app)` called from
  `frontend/__init__.py` (one additive line), keeping `frontend/routes.py`
  largely untouched.
- All pillar imports (`scan_data`, `safety_data`, `scan_launch.get_status`,
  `safety_launch.get_status`) are **lazy** (inside functions), matching the
  existing `routes.py` pattern — no new import cost at app startup and no
  import cycle.

## Data flow

```
user picks model on /pipeline (or /eval-run/new, /benchmarks/new)
      │
      ▼
pipeline.stage_state(model, source)  ── reads ──▶ scan_result.json
      │                                           merged_safety_result.json
      ▼
badges + enabled/disabled launch buttons
      │
 launch POST
      ▼
route → pipeline.require_ready_for_downstream(model, source)
      │ cleared?  no ──▶ 400 with reason + link to the missing stage
      │           yes ─▶ existing start_run(...)
```

## Error handling

- All gate errors are HTML-escaped before rendering (reflected-value XSS
  boundary, same as `eval_launch.validate_launch`).
- Missing / unreadable / incomplete artifacts → gate not cleared, with a
  specific reason ("safety run not complete yet", "scan tier=high; blocked",
  "no safety run found — run red-teaming first").
- Reading any pillar artifact is wrapped so a malformed file never 500s the
  page — it degrades to "missing/blocked".

## Testing

- `unit_tests/test_pipeline.py` (new): `validate_safety_gate` and
  `stage_state` / `require_ready_for_downstream` across source × state
  (cleared, missing, incomplete, wrong-tier, unreadable), using temp artifact
  dirs — mirrors the existing scan-gate tests.
- Extend the eval-launch tests for the new gateway safety gate (blocked until
  a low-tier safety artifact exists).
- Benchmark-gate enforcement + its tests are handled separately by the
  evaluator owner — not in this implementation.

## Out of scope

- Serving HF models for safety red-teaming (HF-safety gap).
- Auto-chaining / background orchestration.
- A persistent model registry / new DB tables.
- Any edit to `scanner/`, `safety/`, `scan_launch.py`, or `safety_launch.py`.
- Benchmark enforcement (`benchmark_launch.py` / benchmark route) — wired
  separately by the evaluator owner.
