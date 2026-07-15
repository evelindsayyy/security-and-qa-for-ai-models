# Model Report Cards: Selector + PDF Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the Report-cards page behind a searchable model picker, remove the featured card from the overview, and add a browser-printable comprehensive PDF report per model.

**Architecture:** `/labels` becomes a searchable launcher (native `<datalist>`) that resolves a model name → its detail slug and redirects to the existing `/models/<slug>` report. That page gains a **Download PDF** button opening a new standalone print route `/models/<slug>/report`, which re-renders the existing `model_rollup` + `model_summary` + eval detail data as a chrome-free document and auto-calls `window.print()`.

**Tech Stack:** Flask + Jinja2, vanilla JS, Tailwind tokens. Tests: `unittest` + `create_app` test client (mirrors `unit_tests/test_routes_compare.py`).

## Global Constraints

- No new Python dependency. PDF = browser Save-as-PDF via `window.print()`.
- Reuse `model_rollup.get_model_rollup`, `model_summary.get_recommendation_summary`, `eval_run_data.get_model_detail`/`get_all_model_cards`. No new pillar logic.
- Every pillar block is N/A-safe (renders "—"/"No … on record" when a pillar has no data). Never 500.
- Navigation slug for `/models/<slug>` is the gateway-normalized form — card field `detail_slug` (NOT `slug`).
- Task display names use the existing `suite_display` field already stamped on eval runs.
- Run tests from repo root with `.venv/bin/python -m pytest <path> -v`.

---

### Task 1: Searchable launcher for `/labels`

**Files:**
- Modify: `frontend/routes.py` (the `model_labels` view, ~lines 149-158)
- Modify: `frontend/templates/model_cards.html` (replace grid with picker)
- Test: `unit_tests/test_routes_labels.py` (create)

**Interfaces:**
- Consumes: `eval_run_data.get_all_model_cards()` → `list[dict]`, each with `detail_slug: str` and `model: str`.
- Produces: `/labels` renders a `<datalist>`-backed picker; `/labels?model=<name-or-slug>` redirects to `url_for('model_detail', slug=detail_slug)` on a match, else re-renders with a `not_found` note.

- [ ] **Step 1: Write the failing test**

Create `unit_tests/test_routes_labels.py`:

```python
"""Tests for /labels — the searchable model-report launcher (routes.py::model_labels)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import eval_run_data  # noqa: E402

_CARDS = [
    {"slug": "GPT-4.1-Mini", "detail_slug": "gpt-4.1-mini", "model": "GPT 4.1 Mini"},
    {"slug": "Llama-3.3", "detail_slug": "llama-3.3", "model": "Llama 3.3"},
]


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class LabelsLauncherTest(unittest.TestCase):
    def test_shows_picker_not_grid(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        self.assertIn("GPT 4.1 Mini", html)
        self.assertIn("<datalist", html)
        self.assertNotIn("mlabel-grid", html)  # the old all-cards grid is gone

    def test_redirects_by_slug(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels?model=llama-3.3")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/models/llama-3.3", resp.headers["Location"])

    def test_redirects_by_display_name_case_insensitive(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels?model=gpt 4.1 mini")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/models/gpt-4.1-mini", resp.headers["Location"])

    def test_unknown_model_rerenders_with_note(self) -> None:
        with mock.patch.object(eval_run_data, "get_all_model_cards", return_value=_CARDS):
            resp = _client().get("/labels?model=nope")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("nope", resp.data.decode())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest unit_tests/test_routes_labels.py -v`
Expected: FAIL (redirect tests get 200 not 302; `<datalist` / `mlabel-grid` assertions fail against the current grid template).

- [ ] **Step 3: Rewrite the `model_labels` route**

In `frontend/routes.py`, replace the whole `model_labels` view with:

```python
    @app.route("/labels")
    def model_labels():
        from flask import redirect, request, url_for
        from frontend.eval_run_data import get_all_model_cards

        try:
            cards = get_all_model_cards()
        except Exception:  # noqa: BLE001 — launcher degrades to empty, never 500s
            cards = []
        models = [
            {"slug": c["detail_slug"], "name": c["model"]}
            for c in cards
            if c.get("detail_slug") and c.get("model")
        ]

        query = (request.args.get("model") or "").strip()
        if query:
            match = next(
                (
                    m
                    for m in models
                    if m["slug"] == query or m["name"].lower() == query.lower()
                ),
                None,
            )
            if match:
                return redirect(url_for("model_detail", slug=match["slug"]))
            return render_template("model_cards.html", models=models, not_found=query)
        return render_template("model_cards.html", models=models, not_found=None)
```

- [ ] **Step 4: Rewrite `model_cards.html` as the picker**

Replace the entire contents of `frontend/templates/model_cards.html` with:

```html
{% extends "base.html" %}
{% from '_macros.html' import page_header, empty_state with context %}

{% block title %}Model report cards — Model Advisor{% endblock %}

{% block breadcrumbs %}
<span><a href="{{ url_for('index') }}">Overview</a></span>
<span class="text-text-subtle">›</span>
<span class="breadcrumb-current">Report cards</span>
{% endblock %}

{% block content %}
{{ page_header(
     'Model report cards',
     'Choose a model to see its full report card — file-scan security, red-team safety, task efficacy, and benchmarks in one page, with a downloadable PDF.'
   ) }}

{% if models %}
<form class="card p-5 mb-6 flex flex-wrap items-end gap-3" method="get" action="{{ url_for('model_labels') }}">
  <label class="flex-1 min-w-[16rem]">
    <span class="block text-sm font-semibold text-text mb-1">Model</span>
    <input class="w-full rounded-lg border border-border px-3 py-2" type="text" name="model"
           list="report-model-names" placeholder="Type or pick a model…"
           value="{{ not_found or '' }}" autocomplete="off" autofocus required>
    <datalist id="report-model-names">
      {% for m in models %}
      <option value="{{ m.name }}"></option>
      {% endfor %}
    </datalist>
  </label>
  <button type="submit" class="btn-primary btn-sm">View report →</button>
  {% if not_found %}
  <p class="w-full text-sm text-text-muted">⚠ No evaluated model matches “{{ not_found }}”. Pick one from the list.</p>
  {% endif %}
</form>
<p class="body">
  {{ models|length }} model{{ "" if models|length == 1 else "s" }} evaluated ·
  <a class="font-semibold text-duke-blue" href="{{ url_for('compare_models') }}">Compare models →</a> ·
  <a class="font-semibold text-duke-blue" href="{{ url_for('models_catalog') }}">Full catalog →</a>
</p>
{% else %}
{{ empty_state('No model report cards yet — a card appears here once a model has at least one eval run.') }}
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest unit_tests/test_routes_labels.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/routes.py frontend/templates/model_cards.html unit_tests/test_routes_labels.py
git commit -m "feat(frontend): searchable model launcher for the report-cards page"
```

---

### Task 2: Remove the featured report card from the overview

**Files:**
- Modify: `frontend/templates/index.html` (remove the featured card section + its now-unused import)
- Modify: `frontend/routes.py` (`_hub_context`, ~lines 101-118 — drop the `model_card` computation and key)
- Test: add `OverviewNoFeaturedCardTest` to `unit_tests/test_routes_labels.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GET /` no longer contains the `mlabel-featured` markup; `_hub_context()` no longer returns a `model_card` key.

- [ ] **Step 1: Write the failing test**

Append to `unit_tests/test_routes_labels.py`:

```python
class OverviewNoFeaturedCardTest(unittest.TestCase):
    def test_overview_has_no_featured_report_card(self) -> None:
        with mock.patch(
            "frontend.routes.get_gateway_catalog",
            return_value={"models": [], "count": 0, "error": None},
        ):
            resp = _client().get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("mlabel-featured", resp.data.decode())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest unit_tests/test_routes_labels.py::OverviewNoFeaturedCardTest -v`
Expected: FAIL (`mlabel-featured` is still present in the rendered overview).

- [ ] **Step 3: Remove the featured section from `index.html`**

In `frontend/templates/index.html`, delete this entire block:

```html
<section class="card p-5 mb-8">
  <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
    <div>
      <h2 class="section-title">Model report cards</h2>
      <p class="body mt-1">One at-a-glance label per model — file-scan security, red-team safety, and task efficacy combined.</p>
    </div>
    <a class="btn-secondary btn-sm" href="{{ url_for('model_labels') }}">Browse all report cards →</a>
  </div>
  {% if model_card %}
  {{ model_label_styles() }}
  <div class="mlabel-featured">{{ model_label_card(model_card) }}</div>
  {% else %}
  <p class="body">No model report cards yet — run an eval to generate the first one.</p>
  {% endif %}
</section>
```

Then delete the now-unused import line near the top of `index.html`:

```html
{% from '_model_label_card.html' import model_label_styles, model_label_card with context %}
```

- [ ] **Step 4: Drop `model_card` from `_hub_context` in `routes.py`**

In `frontend/routes.py`, delete this block from `_hub_context`:

```python
    # Featured per-model report card (the AI Model Advisor label). Best-effort:
    # the home page never breaks if a pillar's data is missing.
    model_card = None
    try:
        from frontend.eval_run_data import featured_model_slug, get_model_card

        fslug = featured_model_slug()
        if fslug:
            model_card = get_model_card(fslug)
    except Exception:
        model_card = None

```

And remove the `"model_card": model_card,` line from the dict returned just below it (the `return {` block).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest unit_tests/test_routes_labels.py -v`
Expected: PASS (all Task 1 + the new overview test).

- [ ] **Step 6: Commit**

```bash
git add frontend/templates/index.html frontend/routes.py unit_tests/test_routes_labels.py
git commit -m "feat(frontend): drop featured report card from overview (sidebar-only entry)"
```

---

### Task 3: Print report route, template, and Download button

**Files:**
- Create: `frontend/templates/model_report_print.html`
- Modify: `frontend/routes.py` (add `model_report_print` view after the `model_detail` view, ~line 1520)
- Modify: `frontend/templates/model_detail.html` (Download PDF button after `page_header`, ~line 21)
- Test: `unit_tests/test_model_report_print.py` (create)

**Interfaces:**
- Consumes: `model_rollup.get_model_rollup(slug) -> dict | None` with `display_name`, `scan{tier, overall_risk_score}`, `safety{tier, pass_rate}`, `benchmark{kinds: {name: {headline_display}}}`; `model_summary.get_recommendation_summary(rollup) -> {sections:[{label,text}], summary, tradeoffs:[str]}`; `eval_run_data.get_model_detail(slug) -> {model, runs:[{suite_display, judge_model, overall}]}`.
- Produces: `GET /models/<slug>/report` renders a standalone printable document; unknown slug renders a printable "Model not found" (200, not 500).

- [ ] **Step 1: Write the failing test**

Create `unit_tests/test_model_report_print.py`:

```python
"""Tests for /models/<slug>/report — the printable PDF report (routes.py::model_report_print)."""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("FRONTEND_LAUNCH_MODE", "host")

from frontend import create_app  # noqa: E402
from frontend import model_rollup, model_summary  # noqa: E402
from frontend import eval_run_data  # noqa: E402

_ROLLUP = {
    "slug": "gpt-4.1-mini", "display_name": "GPT 4.1 Mini",
    "scan": {"tier": "low", "overall_risk_score": 12},
    "safety": {"tier": "low", "pass_rate": 0.9},
    "benchmark": {"kinds": {"mmlu": {"headline_display": "60.0%"}}},
}
_DETAIL = {
    "model": "GPT 4.1 Mini",
    "runs": [{"suite_display": "IT Support", "judge_model": "Llama 4 Maverick", "overall": 4.2}],
}
_REC = {
    "sections": [{"label": "Recommended use", "text": "Good for chat."}],
    "summary": "Solid model.", "tradeoffs": ["Higher cost than open models."],
}


def _client():
    return create_app(test_config={"TESTING": True}).test_client()


class ReportPrintTest(unittest.TestCase):
    def test_known_model_renders_all_pillars(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", return_value=_ROLLUP), \
             mock.patch.object(model_summary, "get_recommendation_summary", return_value=_REC), \
             mock.patch.object(eval_run_data, "get_model_detail", return_value=_DETAIL):
            resp = _client().get("/models/gpt-4.1-mini/report")
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode()
        for needle in ["GPT 4.1 Mini", "Recommended use", "IT Support", "60.0%",
                       "90%", "window.print"]:
            self.assertIn(needle, html)

    def test_unknown_model_is_printable_not_500(self) -> None:
        with mock.patch.object(model_rollup, "get_model_rollup", return_value=None):
            resp = _client().get("/models/nope/report")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Model not found", resp.data.decode())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest unit_tests/test_model_report_print.py -v`
Expected: FAIL with 404 (route not registered yet).

- [ ] **Step 3: Create the print template**

Create `frontend/templates/model_report_print.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% if missing %}Model not found{% else %}{{ model }} — report{% endif %}</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
           color: #111; background: #fff; margin: 0; padding: 2rem; line-height: 1.5; }
    .report { max-width: 760px; margin: 0 auto; }
    h1 { font-size: 1.6rem; margin: 0 0 .25rem; }
    h2 { font-size: 1.05rem; margin: 1.5rem 0 .5rem; border-bottom: 1px solid #ccc; padding-bottom: .25rem; }
    .meta { color: #555; font-size: .85rem; margin-bottom: 1rem; }
    dt { font-weight: 600; margin-top: .5rem; }
    dd { margin: 0 0 .25rem; }
    .rec-summary { white-space: pre-wrap; }
    table { width: 100%; border-collapse: collapse; font-size: .9rem; }
    th, td { text-align: left; padding: .3rem .5rem; border-bottom: 1px solid #eee; }
    .pillar { margin-bottom: 1rem; }
    .na { color: #888; }
    .toolbar { margin-bottom: 1.5rem; }
    button { font-size: .9rem; padding: .4rem .8rem; cursor: pointer; }
    ul { margin: .3rem 0; padding-left: 1.2rem; }
    @media print {
      .toolbar { display: none; }
      body { padding: 0; }
      h2 { page-break-after: avoid; }
      .pillar { page-break-inside: avoid; }
    }
  </style>
</head>
<body>
  <div class="report">
    <div class="toolbar">
      <button type="button" onclick="window.print()">⬇ Print / Save as PDF</button>
    </div>
    {% if missing %}
    <h1>Model not found</h1>
    <p class="na">No rollup data for <code>{{ slug }}</code>.</p>
    {% else %}
    <h1>{{ model }}</h1>
    <p class="meta">Cross-pillar model report · Generated {{ generated_utc }} UTC</p>

    <h2>Recommendation</h2>
    {% if recommendation.sections %}
    <dl>
      {% for s in recommendation.sections %}
      <dt>{{ s.label }}</dt>
      <dd>{{ s.text }}</dd>
      {% endfor %}
    </dl>
    {% endif %}
    {% if recommendation.summary %}
    <p class="rec-summary">{{ recommendation.summary }}</p>
    {% endif %}
    {% if recommendation.tradeoffs %}
    <ul>
      {% for t in recommendation.tradeoffs %}<li>{{ t }}</li>{% endfor %}
    </ul>
    {% endif %}
    {% if not recommendation.sections and not recommendation.summary %}
    <p class="na">No recommendation available yet.</p>
    {% endif %}

    <h2>Security — file scan</h2>
    <div class="pillar">
      {% if rollup.scan %}
      <p>Risk tier: <b>{{ rollup.scan.tier }}</b> · risk score {{ rollup.scan.overall_risk_score }}</p>
      {% else %}<p class="na">No scan on record.</p>{% endif %}
    </div>

    <h2>Safety — red-team</h2>
    <div class="pillar">
      {% if rollup.safety %}
      <p>Tier: <b>{{ rollup.safety.tier }}</b> · pass rate {{ '%.0f%%'|format(rollup.safety.pass_rate * 100) }}</p>
      {% else %}<p class="na">No safety run on record.</p>{% endif %}
    </div>

    <h2>Eval — task suites</h2>
    <div class="pillar">
      {% if detail.runs %}
      <table>
        <thead><tr><th>Tasks</th><th>Judge</th><th>Overall</th></tr></thead>
        <tbody>
        {% for r in detail.runs %}
          <tr>
            <td>{{ r.suite_display }}</td>
            <td>{{ r.judge_model }}</td>
            <td>{{ '%.2f'|format(r.overall) if r.overall is not none else '—' }} / 5</td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}<p class="na">No eval runs on record.</p>{% endif %}
    </div>

    <h2>Benchmarks</h2>
    <div class="pillar">
      {% if rollup.benchmark and rollup.benchmark.kinds %}
      <table>
        <thead><tr><th>Benchmark</th><th>Result</th></tr></thead>
        <tbody>
        {% for kind, info in rollup.benchmark.kinds.items() %}
          <tr><td>{{ kind }}</td><td>{{ info.headline_display or '—' }}</td></tr>
        {% endfor %}
        </tbody>
      </table>
      {% else %}<p class="na">No benchmark runs on record.</p>{% endif %}
    </div>

    <p class="meta" style="margin-top:2rem;">Generated from the Model Advisor dashboard.</p>
    {% endif %}
  </div>
  {% if not missing %}
  <script>window.addEventListener("load", function () { window.print(); });</script>
  {% endif %}
</body>
</html>
```

- [ ] **Step 4: Add the print route to `routes.py`**

Immediately after the `model_detail` view's closing (the `return render_template("model_detail.html", ...)` block, ~line 1520), add:

```python
    @app.route("/models/<slug>/report")
    def model_report_print(slug):
        from datetime import datetime, timezone

        from frontend import model_rollup, model_summary
        from frontend.eval_run_data import get_model_detail

        rollup = model_rollup.get_model_rollup(slug)
        if rollup is None:
            return render_template("model_report_print.html", missing=True, slug=slug)
        detail = get_model_detail(slug) or {"model": rollup["display_name"], "runs": []}
        recommendation = model_summary.get_recommendation_summary(rollup)
        generated_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        return render_template(
            "model_report_print.html",
            missing=False,
            slug=slug,
            model=rollup["display_name"],
            rollup=rollup,
            detail=detail,
            recommendation=recommendation,
            generated_utc=generated_utc,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest unit_tests/test_model_report_print.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Add the Download PDF button to `model_detail.html`**

In `frontend/templates/model_detail.html`, in the `{% else %}` (found) branch, right after this line:

```html
    {{ page_header(model, gateway_profile or 'Cross-pillar nutrition label') }}
```

insert:

```html
    <p class="mb-6">
      <a class="btn-secondary btn-sm" href="{{ url_for('model_report_print', slug=slug) }}"
         target="_blank" rel="noopener">⬇ Download PDF</a>
    </p>
```

(`slug` and `model` are already in the detail context via `**detail`.)

- [ ] **Step 7: Full regression + manual check**

Run: `.venv/bin/python -m pytest unit_tests -q`
Expected: PASS (existing suite + the new tests).

Manual: start the app, open a model detail page, click **Download PDF** — a new tab opens the chrome-free report and the browser print dialog appears; "Save as PDF" produces the document.

- [ ] **Step 8: Commit**

```bash
git add frontend/routes.py frontend/templates/model_report_print.html frontend/templates/model_detail.html unit_tests/test_model_report_print.py
git commit -m "feat(frontend): printable per-model PDF report + Download button"
```

---

## Self-Review

- **Spec coverage:** overview removal (Task 2), `/labels` searchable combobox (Task 1), reuse `/models/<slug>` + Download button (Task 3), new print route/template with all four pillars + recommendation (Task 3), no new dependency (browser print), tests for each (all tasks). ✅
- **Placeholder scan:** none — every step has full code/commands.
- **Type consistency:** `detail_slug`/`model` (card), `suite_display`/`judge_model`/`overall` (runs), `rollup.scan/safety/benchmark`, `recommendation.sections/summary/tradeoffs` — consistent across route, template, and tests.
- **Known gap (accepted):** the Download button's presence in `model_detail.html` has no dedicated automated test (the `model_detail` route has heavy dependencies to mock); it is covered by the Step 7 manual check. The report route it targets is fully tested.
