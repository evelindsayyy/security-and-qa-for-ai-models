# Model report cards: selector-gated entry + PDF export

**Date:** 2026-07-14
**Status:** Approved (design), pending implementation plan
**Scope:** Frontend (report-card flow). Touches shared scaffold (`index.html`, `routes.py`)
and report-card files (`model_cards.html`, `model_detail.html`, `model_rollup`/`model_summary`).

## Problem

Today the overview page shows a featured "Model report cards" section, and the
**Report cards** nav button (`/labels`) renders a grid of *every* evaluated
model's card at once. Two issues:

1. The overview shouldn't carry the report-cards block — it belongs behind the
   sidebar button only.
2. The all-cards grid is crowded. Users should first **choose one model**, then
   see that model's report, and be able to **download a comprehensive PDF** of
   its cross-pillar results (security, safety, eval, benchmarks) — the same
   "recommendation / summary" a user gets when they click into the model name.

## Goals

- Remove the "Model report cards" section from the overview page.
- Turn `/labels` into a **searchable model launcher**: a type-to-filter combobox
  of evaluated models; picking one navigates to that model's report.
- Make `/models/<slug>` the single canonical model report (it already is) and add
  a **Download PDF** action there, so every path into a model (catalog, eval
  table, compare, the new launcher) gets the export.
- The PDF is produced via **browser Save-as-PDF**: a print-optimized report view
  that drops the app chrome and lays out a clean, comprehensive one-document
  report, then triggers `window.print()`.

## Non-goals

- No new Python dependency (no reportlab/WeasyPrint). PDF = browser print.
- No changes to how pillar data is computed. Reuse `model_rollup` +
  `model_summary`.
- No changes to other pillars' pages (scan/safety/eval/benchmark detail).

## Design

### 1. Overview page (`frontend/templates/index.html`, `frontend/routes.py`)

- Remove the `<section>` that renders `model_label_card(model_card)` (the featured
  report card) from `index.html`.
- Remove the now-unused `model_card` / `featured_model_slug` context from the
  index route in `routes.py`. Leave `featured_model_slug()` in the data layer
  (harmless; may be reused) but stop calling it from the index route.
- The sidebar **Report cards** link (`/labels`) is unchanged and remains the only
  entry point.

### 2. Report cards launcher (`/labels`, `frontend/templates/model_cards.html`)

Replace the all-cards grid with:

- A short prompt ("Choose a model to see its report card.").
- A **searchable combobox**: a text `<input list="...">` bound to a native
  `<datalist>` of evaluated model names (zero-dependency type-ahead,
  accessible). A small vanilla-JS handler resolves the typed/selected name to
  its slug and navigates on submit.
- Options come from `get_all_model_cards()` — each card yields a
  `(slug, display_name)` pair. The input matches on display name; on submit /
  selection we navigate to `url_for('model_detail', slug=slug)`.
- Empty state unchanged ("No model report cards yet …") when there are no cards.
- Keep the existing "Compare models →" / "Full catalog →" quick links.

Route (`routes.py::model_labels`): instead of passing `cards` for a grid, pass a
lightweight `models` list of `{slug, name}` for the combobox. A GET with a
`?model=<slug>` (or form submit) redirects to the model detail page.

### 3. Model detail: Download PDF (`frontend/templates/model_detail.html`)

- Add a **Download PDF** button in the page header actions area.
- The button is a link to `/models/<slug>/report` that opens in a **new tab**
  (`target="_blank"`), so the interactive detail page is preserved. The report
  view auto-prints on load (see below).

### 4. Print report view (new route + template)

- **Route:** `GET /models/<slug>/report` →
  `model_report_print(slug)` in `routes.py`.
- Reuses the same data the detail route already assembles:
  `model_rollup.get_model_rollup(slug)`,
  `model_summary.get_recommendation_summary(rollup)`,
  `get_model_detail(slug)`, and `get_model_findings(rollup)`.
- **Template:** `frontend/templates/model_report_print.html` — a standalone
  page (does NOT extend `base.html`, so no sidebar/topbar). Print-optimized CSS
  (inline or a dedicated `print.css`), black-on-white, page-break-friendly.
- **Content (comprehensive, one document):**
  1. Header: model display name, gateway profile, and a static generated-at
     timestamp shown as `Generated <YYYY-MM-DD HH:MM> UTC`. The print page is
     self-contained and does not load `localtime.js`, so UTC is used explicitly
     (no client-side timezone conversion in the PDF).
  2. Recommendation / summary: `recommendation.sections`, `recommendation.summary`,
     `recommendation.tradeoffs`.
  3. Per-pillar results, each a short block:
     - **Security (scan):** overall risk score + severity tier + findings count.
     - **Safety:** pass rate + tier.
     - **Eval:** average overall + per-task (suite) scores, using the clean
       task display names (`suite_display`).
     - **Benchmarks:** headline result(s).
  4. Footer: source note ("Generated from the Model Advisor dashboard").
- On load, a tiny inline script calls `window.print()`. A visible "Print / Save
  as PDF" button is also present as a fallback (and for re-print).

### Data flow

```
/labels (launcher)
  └─ combobox (get_all_model_cards → slug + name)
        └─ navigate → /models/<slug>  (existing comprehensive report)
                          └─ "Download PDF" → /models/<slug>/report
                                                 └─ print-optimized template
                                                       └─ window.print() → Save as PDF
```

No new data sources; the print route is a thin re-render of the rollup the detail
route already builds.

## Error handling

- `/models/<slug>/report` for an unknown/unevaluated slug: render a minimal
  "Model not found" print page (mirror `model_detail` missing behavior), still
  printable, no crash.
- Combobox submit with an empty/invalid model: stay on `/labels` with the prompt
  (no redirect); never 500.
- Missing pillar data (a model with no safety/benchmark yet): each pillar block
  is N/A-safe and renders "—", matching the detail page.

## Testing

- **Unit/route tests** (`unit_tests/`):
  - `/labels` returns 200 and renders the combobox with the evaluated models;
    no full card grid.
  - `/labels?model=<slug>` redirects to `/models/<slug>`.
  - Overview (`/`) no longer contains the featured report-card markup.
  - `/models/<slug>/report` returns 200 for an evaluated model and contains the
    recommendation + all four pillar blocks; unknown slug renders the missing
    page (not 500).
- **Render smoke test** via the Flask test client for the new template.
- Manual: verify browser "Save as PDF" yields a clean, chrome-free document.

## Files touched

| File | Change |
|---|---|
| `frontend/templates/index.html` | remove featured report-card section |
| `frontend/routes.py` | drop featured card from index; slim `model_labels`; add `model_report_print` route |
| `frontend/templates/model_cards.html` | grid → searchable combobox launcher |
| `frontend/templates/model_detail.html` | add Download PDF button |
| `frontend/templates/model_report_print.html` | **new** print-optimized report |
| (optional) `frontend/static/print.css` | print styles if not inlined |

## Scope / ownership note

`index.html` and `routes.py` are shared frontend scaffold; the report-card
templates and `model_rollup`/`model_summary`/`eval_run_data` are Grace's
report-card work. Changes are kept tight and flagged for review.
