-- =============================================================================
-- Benchmarks pillar — PostgreSQL schema
-- =============================================================================
-- Target database: qa_ai_models   Target schema: public
--
-- Design sources:
--   - docs/data-model.md         — benchmark_runs sketch (Track B public benchmarks)
--   - benchmarks/results/        — on-disk JSON / JSONL from run_benchmark.py
--
-- Idempotency keys (loader ON CONFLICT DO NOTHING):
--   benchmark_runs: UNIQUE (output_slug)  — file stem = UI slug
--
-- Deferred: shared `models` table FK on benchmark_runs.model_id.
-- Separate from evaluator/db/ — Duke eval suites use eval_runs, not this table.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- public.benchmark_runs — one row per benchmark result file
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.benchmark_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id            UUID,                       -- nullable; FK to models.id when that table exists
    output_slug         TEXT NOT NULL,              -- file stem (UI slug)
    source_filename     TEXT NOT NULL,              -- e.g. 20250618T120000Z_truthfulqa_gpt-5-chat.json
    gateway_model_id    TEXT NOT NULL,
    benchmark_key       TEXT NOT NULL,              -- truthfulqa | ifeval | mmlu | tomi | consistency | ...
    inference_backend   TEXT NOT NULL DEFAULT 'gateway',
    status              TEXT NOT NULL DEFAULT 'complete',
    headline_metric     TEXT,
    headline_value      DOUBLE PRECISION,
    n_items             INTEGER NOT NULL DEFAULT 0,
    metrics             JSONB NOT NULL DEFAULT '{}'::jsonb,
    items               JSONB NOT NULL DEFAULT '[]'::jsonb,
    run_params          JSONB,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (output_slug)
);

CREATE INDEX IF NOT EXISTS idx_benchmark_runs_gateway_model_id
    ON public.benchmark_runs (gateway_model_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_benchmark_key
    ON public.benchmark_runs (benchmark_key);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_completed_at
    ON public.benchmark_runs (completed_at DESC);
