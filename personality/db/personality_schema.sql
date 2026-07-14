-- =============================================================================
-- Personality pillar — PostgreSQL schema (BFI, compass, future self-report tests)
-- =============================================================================
-- Target database: qa_ai_models   Target schema: public
--
-- Design: flat JSON artifacts under personality/results/ (same envelope as
-- benchmarks). Auth/visibility columns are added by db/auth_schema.sql.
--
-- Idempotency: UNIQUE (output_slug) — file stem = UI slug.
-- Not part of model rollup / aggregate score.
-- =============================================================================


CREATE TABLE IF NOT EXISTS public.personality_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    output_slug         TEXT NOT NULL,              -- file stem (UI slug)
    source_filename     TEXT NOT NULL,
    gateway_model_id    TEXT NOT NULL,
    test_key            TEXT NOT NULL,              -- bfi | compass | …
    status              TEXT NOT NULL DEFAULT 'complete',
    n_items             INTEGER NOT NULL DEFAULT 0,
    attempted           INTEGER,
    scored              INTEGER,
    coverage            DOUBLE PRECISION,
    traits              JSONB NOT NULL DEFAULT '{}'::jsonb,
    items               JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary             JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (output_slug)
);

CREATE INDEX IF NOT EXISTS idx_personality_runs_gateway_model_id
    ON public.personality_runs (gateway_model_id);
CREATE INDEX IF NOT EXISTS idx_personality_runs_test_key
    ON public.personality_runs (test_key);
CREATE INDEX IF NOT EXISTS idx_personality_runs_completed_at
    ON public.personality_runs (completed_at DESC);
