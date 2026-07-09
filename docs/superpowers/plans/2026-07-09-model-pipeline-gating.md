# Model Pipeline Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A model must clear security scanning (HF repos) or safety red-teaming (gateway models) before it can be evaluated or benchmarked, enforced as a server-side hard block.

**Architecture:** One new module `frontend/pipeline.py` is the single source of truth for the gates — it reads the scanner + safety artifacts read-only and defines "cleared" once (completed artifact, headline tier `low`). Gateway eval launches gain a safety gate in the eval routes; a new read-only `/pipeline` page shows each model's stage state. No pillar code (`scanner/`, `safety/`, `scan_launch.py`, `safety_launch.py`) is edited; benchmark enforcement is wired separately by the evaluator owner and is out of this plan.

**Tech Stack:** Python 3, Flask, `unittest` (run via `uv run python -m unittest`), `markupsafe.escape` for reflected values.

## Global Constraints

- Gate "cleared" = artifact `status` in `{"complete", "completed"}` AND headline tier == `"low"`. Safety headline field is `composite_tier`; scan field is `severity_tier`.
- Source-aware: `gateway` → scan N/A, safety required; `hf` → scan required, safety `unsupported` (not required — HF-safety is out of scope).
- All pillar imports (`safety.*`, `scanner.*`, `frontend.scan_data`, `frontend.eval_launch`, `gateway.catalog`) are **lazy** (inside functions) to avoid startup cost and the `pipeline ↔ eval_launch` import cycle — matches the `frontend/routes.py` pattern.
- Every reflected user value in a gate error is wrapped in `markupsafe.escape` (errors render as HTML).
- Tests are `unittest`, offline/deterministic (no network, no real subprocess, no real artifacts — use temp files + `mock`). Run from repo root.
- Do NOT edit `scanner/`, `safety/`, `frontend/scan_launch.py`, `frontend/safety_launch.py`, `frontend/benchmark_launch.py`, or the benchmark route.
- Do NOT `git push` (commits only).

---

### Task 1: Safety gate reader (`validate_safety_gate`)

**Files:**
- Create: `frontend/pipeline.py`
- Test: `unit_tests/test_pipeline.py`

**Interfaces:**
- Consumes: `safety.gateway_ids.normalize_gateway_model_id(model) -> str`; `safety.merged_paths.merged_result_path(output_dir: Path, slug: str, profile: str) -> Path`. Safety artifact JSON has `status` (defaults `"complete"`) and `composite_tier` (`"low"|"medium"|"high"|"critical"`).
- Produces: `validate_safety_gate(model: str, *, profile: str = "base") -> dict` with keys `model, profile, path, status, tier, ok, error`. `ok=True` only when the artifact exists, is readable, `status ∈ {"complete","completed"}`, and `tier == "low"`. `status` is `None` when the file is missing (used by Task 4 to distinguish "missing" from "blocked"). Also produces module constants `CLEARED_TIER="low"`, `COMPLETE_STATUSES=frozenset({"complete","completed"})`, `DEFAULT_SAFETY_PROFILE="base"`, `SAFETY_OUTPUT_DIR`, and helper `_safety_result_path(model, profile) -> Path`.

- [ ] **Step 1: Write the failing test**

Create `unit_tests/test_pipeline.py`:

```python
"""
Tests for the cross-pillar launch gates in frontend/pipeline.py.

Offline + deterministic: safety artifacts are written to a temp dir and
_safety_result_path is patched to point at them (no real safety/output, no
dependency on normalize_gateway_model_id here).

Run from repo root:
  uv run python -m unittest unit_tests.test_pipeline -v
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from frontend import pipeline


def _write_safety(tmp: Path, payload: dict) -> Path:
    p = tmp / "merged_safety_result.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


class ValidateSafetyGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _patch_path(self, path: Path) -> None:
        p = mock.patch.object(pipeline, "_safety_result_path", return_value=path)
        p.start()
        self.addCleanup(p.stop)

    def test_complete_low_tier_clears(self) -> None:
        self._patch_path(_write_safety(self.tmp, {"status": "complete", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertTrue(gate["ok"])
        self.assertIsNone(gate["error"])

    def test_missing_file_blocks_with_none_status(self) -> None:
        self._patch_path(self.tmp / "does_not_exist.json")
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIsNone(gate["status"])
        self.assertIn("safety red-teaming required", gate["error"])

    def test_incomplete_status_blocks(self) -> None:
        self._patch_path(_write_safety(self.tmp, {"status": "running", "composite_tier": "low"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("not complete", gate["error"])

    def test_high_tier_blocks(self) -> None:
        self._patch_path(_write_safety(self.tmp, {"status": "complete", "composite_tier": "high"}))
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("did not clear", gate["error"])

    def test_unreadable_blocks(self) -> None:
        path = self.tmp / "merged_safety_result.json"
        path.write_text("{ not json", encoding="utf-8")
        self._patch_path(path)
        gate = pipeline.validate_safety_gate("Llama 4 Maverick")
        self.assertFalse(gate["ok"])
        self.assertIn("unreadable", gate["error"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest unit_tests.test_pipeline -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'frontend.pipeline'` (or `AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/pipeline.py`:

```python
"""
Cross-pillar launch gates: a model must clear the earlier pillars before it can
be evaluated or benchmarked.

Read-only over the scanner + safety artifacts. This module never runs, edits, or
imports the pillars' launch code at import time — every pillar import is lazy
(inside a function), matching frontend/routes.py. "Cleared" is defined once here
and mirrors the scanner gate in eval_launch.validate_hf_scan_gate: a completed
artifact whose headline tier is 'low'.

Source-aware:
  gateway model -> nothing to scan (N/A); must clear safety red-teaming.
  hf repo       -> must clear the artifact scan; safety red-teaming is not yet
                   supported for served HF models (out of scope), so it is not
                   required for HF.
"""

from __future__ import annotations

import json
from pathlib import Path

from markupsafe import escape

ROOT = Path(__file__).parent.parent
SAFETY_OUTPUT_DIR = ROOT / "safety" / "output"

CLEARED_TIER = "low"
COMPLETE_STATUSES = frozenset({"complete", "completed"})
DEFAULT_SAFETY_PROFILE = "base"


def _safety_result_path(model: str, profile: str = DEFAULT_SAFETY_PROFILE) -> Path:
    """Published safety artifact for a gateway model id (read-only)."""
    from safety.gateway_ids import normalize_gateway_model_id
    from safety.merged_paths import merged_result_path

    slug = normalize_gateway_model_id(model)
    return merged_result_path(SAFETY_OUTPUT_DIR, slug, profile)


def validate_safety_gate(model: str, *, profile: str = DEFAULT_SAFETY_PROFILE) -> dict:
    """Require a completed, low-tier safety run before eval/benchmark.

    Mirrors eval_launch.validate_hf_scan_gate: only a completed run whose
    composite_tier is 'low' clears the gate. Reflected values are HTML-escaped
    (errors render as HTML).
    """
    path = _safety_result_path(model, profile)
    base = {
        "model": model,
        "profile": profile,
        "path": str(path),
        "status": None,
        "tier": None,
    }
    if not path.is_file():
        return {
            **base,
            "ok": False,
            "error": (
                "safety red-teaming required before this step; run safety for "
                f"'{escape(model)}' first, then retry"
            ),
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — malformed artifact must never 500
        return {
            **base,
            "ok": False,
            "error": f"safety result is unreadable: {type(e).__name__}: {e}",
        }

    status = str(data.get("status") or "unknown").lower()
    tier = str(data.get("composite_tier") or "unknown").lower()
    out = {**base, "status": status, "tier": tier}
    if status not in COMPLETE_STATUSES:
        return {**out, "ok": False,
                "error": f"safety run is not complete yet (status={status})"}
    if tier != CLEARED_TIER:
        return {
            **out,
            "ok": False,
            "error": (
                "safety red-teaming did not clear this model "
                f"(tier={tier}); eval/benchmark is blocked"
            ),
        }
    return {**out, "ok": True, "error": None}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest unit_tests.test_pipeline -v`
Expected: PASS (5 tests in `ValidateSafetyGateTest`).

- [ ] **Step 5: Commit**

```bash
git add frontend/pipeline.py unit_tests/test_pipeline.py
git commit -m "feat(pipeline): safety launch gate (complete + low tier)"
```

---

### Task 2: Unified prerequisite check (`require_ready_for_downstream`)

**Files:**
- Modify: `frontend/pipeline.py`
- Test: `unit_tests/test_pipeline.py`

**Interfaces:**
- Consumes: `validate_safety_gate` (Task 1); `frontend.eval_launch.validate_hf_scan_gate(repo_id: str) -> dict` (existing — returns `{"ok": bool, "error": str|None, "status": ...}`).
- Produces: `require_ready_for_downstream(model: str, source: str) -> str | None` — returns `None` when the model may proceed, else the blocking error string. `source == "hf"` requires a cleared scan; any other value (`"gateway"`) requires a cleared safety run.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_pipeline.py`:

```python
class RequireReadyTest(unittest.TestCase):
    def test_gateway_cleared_returns_none(self) -> None:
        with mock.patch.object(pipeline, "validate_safety_gate",
                               return_value={"ok": True, "error": None}):
            self.assertIsNone(
                pipeline.require_ready_for_downstream("Llama 4 Maverick", "gateway")
            )

    def test_gateway_blocked_returns_error(self) -> None:
        with mock.patch.object(pipeline, "validate_safety_gate",
                               return_value={"ok": False, "error": "no safety run"}):
            self.assertEqual(
                pipeline.require_ready_for_downstream("Llama 4 Maverick", "gateway"),
                "no safety run",
            )

    def test_hf_scan_cleared_returns_none(self) -> None:
        with mock.patch("frontend.eval_launch.validate_hf_scan_gate",
                        return_value={"ok": True, "error": None}):
            self.assertIsNone(
                pipeline.require_ready_for_downstream("Qwen/Qwen2.5-7B-Instruct", "hf")
            )

    def test_hf_scan_blocked_returns_error(self) -> None:
        with mock.patch("frontend.eval_launch.validate_hf_scan_gate",
                        return_value={"ok": False, "error": "scan required"}):
            self.assertEqual(
                pipeline.require_ready_for_downstream("Qwen/Qwen2.5-7B-Instruct", "hf"),
                "scan required",
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest unit_tests.test_pipeline.RequireReadyTest -v`
Expected: FAIL — `AttributeError: module 'frontend.pipeline' has no attribute 'require_ready_for_downstream'`.

- [ ] **Step 3: Write minimal implementation**

Append to `frontend/pipeline.py`:

```python
def require_ready_for_downstream(model: str, source: str) -> str | None:
    """Hard-block gate reused by eval + benchmark. Returns the blocking error
    message, or None when the model may proceed.

    gateway: safety must be cleared (scan is N/A).
    hf:      scan must be cleared (safety not yet supported for served HF models).
    """
    if source == "hf":
        # Lazy import breaks the pipeline <-> eval_launch cycle.
        from frontend.eval_launch import validate_hf_scan_gate

        gate = validate_hf_scan_gate(model)
        return None if gate["ok"] else gate["error"]

    gate = validate_safety_gate(model)
    return None if gate["ok"] else gate["error"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest unit_tests.test_pipeline -v`
Expected: PASS (all `ValidateSafetyGateTest` + `RequireReadyTest`).

- [ ] **Step 5: Commit**

```bash
git add frontend/pipeline.py unit_tests/test_pipeline.py
git commit -m "feat(pipeline): source-aware require_ready_for_downstream gate"
```

---

### Task 3: Enforce the safety gate on gateway eval launches

**Files:**
- Modify: `frontend/routes.py` (`eval_run_start`, `eval_run_start_custom` — gateway branches only)
- Modify: `unit_tests/test_eval_launch.py` (`LaunchRoutesTest`, `CustomRouteTest`)

**Interfaces:**
- Consumes: `frontend.pipeline.require_ready_for_downstream(candidate, "gateway")` (Task 2).
- Produces: a 400 response with the gate's error text when a gateway eval is launched for a model that hasn't cleared safety. The HF branches are unchanged (they keep the existing scan gate).

**Context:** Today the gateway eval path has NO gate. Adding one changes behavior — every existing gateway eval now requires a cleared safety run first. The existing route tests that post gateway models and expect a 302 spawn must therefore mock the gate as cleared.

- [ ] **Step 1: Write the failing test**

In `unit_tests/test_eval_launch.py`, add a class-wide "gate cleared" patch to `LaunchRoutesTest.setUp` (so existing spawn tests still pass) and a new block test. Find `LaunchRoutesTest.setUp` (around line 214) and insert, right before `self.client = ...`:

```python
        # The gateway eval path now requires a cleared safety gate; keep the
        # existing spawn tests green by treating every model as cleared. The
        # block behavior is exercised in test_start_blocked_when_safety_missing.
        gate = mock.patch(
            "frontend.pipeline.require_ready_for_downstream", return_value=None
        )
        gate.start()
        self.addCleanup(gate.stop)
```

Then add this new test method to `LaunchRoutesTest`:

```python
    def test_start_blocked_when_safety_missing(self) -> None:
        with mock.patch(
            "frontend.pipeline.require_ready_for_downstream",
            return_value="safety red-teaming required before this step",
        ):
            r = self.client.post("/eval-run/start", data={
                "candidate": "GPT 4.1 Mini", "judge": "Llama 4 Maverick",
                "suite": "it_support_v1", "max_tokens": "500",
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn(b"safety red-teaming required", r.data)
```

Also add the same class-wide patch to `CustomRouteTest.setUp` (around line 365), right before `self.client = ...`:

```python
        gate = mock.patch(
            "frontend.pipeline.require_ready_for_downstream", return_value=None
        )
        gate.start()
        self.addCleanup(gate.stop)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest unit_tests.test_eval_launch.LaunchRoutesTest -v`
Expected: FAIL — `test_start_blocked_when_safety_missing` returns 302 (no gate wired yet), asserting 400 fails.

- [ ] **Step 3: Write minimal implementation**

In `frontend/routes.py`, `eval_run_start`, gateway branch: after the `validate_launch` error check and before `start_run`, insert the gate. The block currently reads:

```python
        # Allowlist validation is the security boundary — nothing that
        # fails it may reach subprocess (TASK.md hard constraint).
        error = validate_launch(candidate, judge, suite_key, max_tokens)
        if error is not None:
            return error, 400

        slug, _already = start_run(candidate, judge, suite_key, max_tokens)
```

Change it to:

```python
        # Allowlist validation is the security boundary — nothing that
        # fails it may reach subprocess (TASK.md hard constraint).
        error = validate_launch(candidate, judge, suite_key, max_tokens)
        if error is not None:
            return error, 400

        # Cross-pillar gate: a gateway model must clear safety red-teaming
        # before it can be evaluated (scan is N/A for gateway endpoints).
        from frontend import pipeline

        gate_error = pipeline.require_ready_for_downstream(candidate, "gateway")
        if gate_error is not None:
            return gate_error, 400

        slug, _already = start_run(candidate, judge, suite_key, max_tokens)
```

In `eval_run_start_custom`, gateway branch: the `candidate` is known right after the `max_tokens` parse. Insert the gate BEFORE `validate_custom_questions`/`write_custom_suite` so a blocked model never writes a suite file. The block currently reads:

```python
        candidate = request.form.get("candidate", "")
        judge = request.form.get("judge", "")
        try:
            max_tokens = int(request.form.get("max_tokens", ""))
        except ValueError:
            return "max_tokens must be an integer", 400

        # Validate the user's pasted questions as data before anything touches
        # the filesystem or a subprocess (the custom-content security boundary).
        questions, q_error = validate_custom_questions(request.form.get("questions", ""))
```

Change it to:

```python
        candidate = request.form.get("candidate", "")
        judge = request.form.get("judge", "")
        try:
            max_tokens = int(request.form.get("max_tokens", ""))
        except ValueError:
            return "max_tokens must be an integer", 400

        # Cross-pillar gate before we write any custom-suite file: a gateway
        # model must clear safety red-teaming first (scan is N/A for gateway).
        from frontend import pipeline

        gate_error = pipeline.require_ready_for_downstream(candidate, "gateway")
        if gate_error is not None:
            return gate_error, 400

        # Validate the user's pasted questions as data before anything touches
        # the filesystem or a subprocess (the custom-content security boundary).
        questions, q_error = validate_custom_questions(request.form.get("questions", ""))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m unittest unit_tests.test_eval_launch -v`
Expected: PASS — all existing tests plus `test_start_blocked_when_safety_missing`.

- [ ] **Step 5: Commit**

```bash
git add frontend/routes.py unit_tests/test_eval_launch.py
git commit -m "feat(eval): gate gateway eval launches on cleared safety run"
```

---

### Task 4: Per-model pipeline state (`stage_state` + `build_overview`)

**Files:**
- Modify: `frontend/pipeline.py`
- Test: `unit_tests/test_pipeline.py`

**Interfaces:**
- Consumes: `validate_safety_gate` (Task 1), `frontend.eval_launch.validate_hf_scan_gate` (existing), `gateway.catalog.get_gateway_catalog() -> {"models": [{"id": str, "category": str}, ...]}`, `frontend.scan_data.get_scans_data() -> {"scans": [{"model_id": str, ...}, ...]}`.
- Produces:
  - `stage_state(model: str, source: str) -> dict` with keys `model, source, scan, safety, eval_unlocked`. `scan` and `safety` are each `{"state": str, "detail": str}` where `state ∈ {"n/a","unsupported","missing","running","cleared","blocked"}` (`"running"` is reserved; not emitted in this MVP). `eval_unlocked` is `True` only when the required gate(s) for that source cleared.
  - `build_overview() -> {"rows": list[dict], "has_rows": bool}` — one `stage_state` row per gateway model and per scanned HF repo.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_pipeline.py`:

```python
class StageStateTest(unittest.TestCase):
    def test_gateway_cleared_unlocks_eval(self) -> None:
        with mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": True, "error": None, "status": "complete"},
        ):
            st = pipeline.stage_state("Llama 4 Maverick", "gateway")
        self.assertEqual(st["scan"]["state"], "n/a")
        self.assertEqual(st["safety"]["state"], "cleared")
        self.assertTrue(st["eval_unlocked"])

    def test_gateway_missing_safety_is_missing_and_locked(self) -> None:
        with mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": False, "error": "run safety", "status": None},
        ):
            st = pipeline.stage_state("Llama 4 Maverick", "gateway")
        self.assertEqual(st["safety"]["state"], "missing")
        self.assertFalse(st["eval_unlocked"])

    def test_gateway_blocked_tier_is_blocked(self) -> None:
        with mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": False, "error": "tier high", "status": "complete"},
        ):
            st = pipeline.stage_state("Llama 4 Maverick", "gateway")
        self.assertEqual(st["safety"]["state"], "blocked")
        self.assertFalse(st["eval_unlocked"])

    def test_hf_scan_cleared_safety_unsupported(self) -> None:
        with mock.patch(
            "frontend.eval_launch.validate_hf_scan_gate",
            return_value={"ok": True, "error": None, "status": "complete"},
        ):
            st = pipeline.stage_state("Qwen/Qwen2.5-7B-Instruct", "hf")
        self.assertEqual(st["scan"]["state"], "cleared")
        self.assertEqual(st["safety"]["state"], "unsupported")
        self.assertTrue(st["eval_unlocked"])


class BuildOverviewTest(unittest.TestCase):
    def test_rows_from_gateway_and_scans(self) -> None:
        with mock.patch(
            "gateway.catalog.get_gateway_catalog",
            return_value={"models": [{"id": "Llama 4 Maverick", "category": "general_chat"}]},
        ), mock.patch(
            "frontend.scan_data.get_scans_data",
            return_value={"scans": [{"model_id": "Qwen/Qwen2.5-7B-Instruct", "slug": "Qwen--Qwen2.5-7B-Instruct"}]},
        ), mock.patch.object(
            pipeline, "validate_safety_gate",
            return_value={"ok": False, "error": "run safety", "status": None},
        ), mock.patch(
            "frontend.eval_launch.validate_hf_scan_gate",
            return_value={"ok": True, "error": None, "status": "complete"},
        ):
            ov = pipeline.build_overview()
        self.assertTrue(ov["has_rows"])
        self.assertEqual({r["source"] for r in ov["rows"]}, {"gateway", "hf"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest unit_tests.test_pipeline.StageStateTest unit_tests.test_pipeline.BuildOverviewTest -v`
Expected: FAIL — `AttributeError: module 'frontend.pipeline' has no attribute 'stage_state'`.

- [ ] **Step 3: Write minimal implementation**

Append to `frontend/pipeline.py`:

```python
def _gate_stage(gate: dict) -> dict:
    """Map a gate verdict to a display stage. `status is None` means the
    artifact was absent (missing) vs. present-but-failing (blocked)."""
    if gate["ok"]:
        return {"state": "cleared", "detail": ""}
    if gate.get("status") is None:
        return {"state": "missing", "detail": gate["error"]}
    return {"state": "blocked", "detail": gate["error"]}


def stage_state(model: str, source: str) -> dict:
    """Per-model pipeline state for the /pipeline view (read-only)."""
    if source == "hf":
        from frontend.eval_launch import validate_hf_scan_gate

        scan_gate = validate_hf_scan_gate(model)
        return {
            "model": model,
            "source": source,
            "scan": _gate_stage(scan_gate),
            "safety": {
                "state": "unsupported",
                "detail": "safety red-teaming not yet supported for served HF models",
            },
            "eval_unlocked": scan_gate["ok"],
        }

    safety_gate = validate_safety_gate(model)
    return {
        "model": model,
        "source": source,
        "scan": {"state": "n/a", "detail": "nothing to scan (API endpoint)"},
        "safety": _gate_stage(safety_gate),
        "eval_unlocked": safety_gate["ok"],
    }


def build_overview() -> dict:
    """All gateway models + every HF repo that already has a scan, each with its
    pipeline stage state. Degrades gracefully if a data source is unavailable."""
    rows: list[dict] = []
    try:
        from gateway.catalog import get_gateway_catalog

        for m in get_gateway_catalog().get("models", []):
            rows.append(stage_state(m["id"], "gateway"))
    except Exception:  # noqa: BLE001 — a catalog hiccup must not 500 the page
        pass
    try:
        from frontend.scan_data import get_scans_data

        for s in get_scans_data().get("scans", []):
            repo = s.get("model_id")
            if repo:
                rows.append(stage_state(repo, "hf"))
    except Exception:  # noqa: BLE001
        pass
    return {"rows": rows, "has_rows": bool(rows)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest unit_tests.test_pipeline -v`
Expected: PASS (all classes).

- [ ] **Step 5: Commit**

```bash
git add frontend/pipeline.py unit_tests/test_pipeline.py
git commit -m "feat(pipeline): stage_state + build_overview for the pipeline view"
```

---

### Task 5: `/pipeline` page (route + template + wiring)

**Files:**
- Create: `frontend/pipeline_routes.py`
- Create: `frontend/templates/pipeline.html`
- Modify: `frontend/__init__.py`
- Test: `unit_tests/test_pipeline.py`

**Interfaces:**
- Consumes: `frontend.pipeline.build_overview()` (Task 4).
- Produces: `register_pipeline_routes(app)` registering `GET /pipeline`; a rendered page listing each model's scan/safety/eval stages.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_pipeline.py`:

```python
from frontend import create_app  # noqa: E402  (top-of-file group is fine too)


class PipelineRouteTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = create_app({"TESTING": True}).test_client()

    def test_pipeline_page_renders_empty(self) -> None:
        with mock.patch("frontend.pipeline.build_overview",
                        return_value={"rows": [], "has_rows": False}):
            r = self.client.get("/pipeline")
        self.assertEqual(r.status_code, 200)

    def test_pipeline_page_lists_models(self) -> None:
        rows = [
            {"model": "Llama 4 Maverick", "source": "gateway",
             "scan": {"state": "n/a", "detail": ""},
             "safety": {"state": "missing", "detail": "run safety"},
             "eval_unlocked": False},
        ]
        with mock.patch("frontend.pipeline.build_overview",
                        return_value={"rows": rows, "has_rows": True}):
            r = self.client.get("/pipeline")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Llama 4 Maverick", r.data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest unit_tests.test_pipeline.PipelineRouteTest -v`
Expected: FAIL — `GET /pipeline` returns 404 (route not registered).

- [ ] **Step 3: Write minimal implementation**

Create `frontend/pipeline_routes.py`:

```python
"""Route for the unified model-pipeline view (/pipeline).

Kept separate from frontend/routes.py so the pipeline layer stays self-contained;
registered from frontend/__init__.py alongside the main routes.
"""

from __future__ import annotations

from flask import render_template


def register_pipeline_routes(app):
    @app.route("/pipeline")
    def pipeline_overview():
        from frontend.pipeline import build_overview

        return render_template("pipeline.html", **build_overview())
```

Create `frontend/templates/pipeline.html`:

```html
{% extends "base.html" %}
{% block title %}Model pipeline{% endblock %}
{% block content %}
<h1>Model pipeline</h1>
<p>Each model must clear its prerequisite pillars before eval or benchmark:
gateway models clear <strong>safety red-teaming</strong>; Hugging Face repos
clear <strong>security scanning</strong>.</p>

{% if not has_rows %}
  <p>No models yet. Add a gateway model or run a scan to populate this view.</p>
{% else %}
<table>
  <thead>
    <tr><th>Model</th><th>Source</th><th>Scan</th><th>Safety</th><th>Eval / Benchmark</th></tr>
  </thead>
  <tbody>
    {% for r in rows %}
    <tr>
      <td>{{ r.model }}</td>
      <td>{{ r.source }}</td>
      <td title="{{ r.scan.detail }}">{{ r.scan.state }}</td>
      <td title="{{ r.safety.detail }}">{{ r.safety.state }}</td>
      <td>
        {% if r.eval_unlocked %}
          <a href="{{ url_for('eval_run_new') }}">unlocked</a>
        {% else %}
          locked
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endif %}
{% endblock %}
```

In `frontend/__init__.py`, register the routes. After the existing `register_routes(app)` line, add:

```python
    from frontend.pipeline_routes import register_pipeline_routes

    register_pipeline_routes(app)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest unit_tests.test_pipeline -v`
Expected: PASS (all classes, including `PipelineRouteTest`).

- [ ] **Step 5: Verify base template block name**

Run: `grep -nE "block (content|title)" frontend/templates/base.html`
Expected: shows the block names used by `base.html`. If the content block is not named `content` (or the title block differs), update `pipeline.html`'s `{% block %}` names to match, then re-run Step 4.

- [ ] **Step 6: Commit**

```bash
git add frontend/pipeline_routes.py frontend/templates/pipeline.html frontend/__init__.py unit_tests/test_pipeline.py
git commit -m "feat(pipeline): /pipeline overview page (route + template + wiring)"
```

---

## Self-Review

**Spec coverage:**
- Hard block on gateway eval → Task 3. ✓
- Safety gate "complete + low tier" → Task 1. ✓
- Source-aware (gateway safety / HF scan / HF-safety unsupported) → Tasks 2 & 4. ✓
- `/pipeline` unified view listing gateway + scanned HF models, eval unlocked only when cleared → Task 5 (+ `build_overview` Task 4). ✓
- Read-only over pillar artifacts, lazy imports, no edits to `scanner/`/`safety/`/pillar launch files → all tasks. ✓
- Benchmark handled separately by the evaluator owner → intentionally excluded. ✓
- Reflected-value escaping → Task 1 gate errors use `escape`. ✓

**Placeholder scan:** No TBD/TODO; every code and test step is complete. ✓

**Type consistency:** `validate_safety_gate`/`validate_hf_scan_gate` both return `ok`/`error`/`status`; `_gate_stage` reads `gate["ok"]`/`gate.get("status")`/`gate["error"]` consistently; `require_ready_for_downstream(model, source)` and `stage_state(model, source)` share the `source ∈ {"gateway","hf"}` convention; `build_overview` feeds `m["id"]` (gateway) and `s["model_id"]` (scan) — both verified against the real data modules. ✓

**Known behavior change (flagged):** Task 3 gates all gateway eval launches — existing gateway evals now require a cleared `base`-profile safety run. Existing route tests are updated in the same task to mock the gate.

## Out of Scope (per spec)
- HF-safety execution (serving HF on the DCC for red-teaming).
- Auto-chaining / background orchestration.
- Persistent model registry / new DB tables.
- Benchmark route enforcement (wired separately by the evaluator owner) and any edit to `scanner/`, `safety/`, `scan_launch.py`, `safety_launch.py`.
