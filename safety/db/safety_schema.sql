-- =============================================================================
-- Safety pillar — PostgreSQL schema
-- =============================================================================
-- Target database: qa_ai_models   Target schema: public
--
-- Status: DRAFT for team review. Running this file CREATEs tables in the
-- shared Duke Postgres (codeplus-postgres-test-01). DO NOT run until someone
-- with CREATE rights on `public` has reviewed this.
--
-- Design sources:
--   - docs/data-model.md         — safety_runs / safety_findings sketch
--   - safety/schemas.py          — MergedSafetyResult + SafetyFinding on disk
--
-- Idempotency keys (loader ON CONFLICT DO NOTHING):
--   safety_runs:     UNIQUE (gateway_model_id, completed_at)
--   safety_findings: UNIQUE (run_id, finding_key)  — finding_key = SafetyFinding.id
--
-- Deferred: shared `models` table FK on safety_runs.model_id (same stance as scans).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- public.safety_runs — one merged safety label per gateway model run
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.safety_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id            UUID,                       -- nullable; FK to models.id when that table exists
    gateway_model_id    TEXT NOT NULL,              -- MergedSafetyResult.gateway_model_id
    display_name        TEXT,
    status              TEXT NOT NULL DEFAULT 'complete',
    deployment_context  JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary_pass_rate   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    safety_tier         TEXT NOT NULL,              -- low | medium | high | critical
    adversarial_tier    TEXT NOT NULL,
    composite_tier      TEXT NOT NULL,
    composite_score     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    missing_suites      JSONB NOT NULL DEFAULT '[]'::jsonb,
    runs                JSONB NOT NULL DEFAULT '[]'::jsonb,  -- SafetyRunSummary[]
    tool_results        JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,                -- idempotency key with gateway_model_id
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (gateway_model_id, completed_at)
);

CREATE INDEX IF NOT EXISTS idx_safety_runs_gateway_model_id ON public.safety_runs (gateway_model_id);
CREATE INDEX IF NOT EXISTS idx_safety_runs_completed_at ON public.safety_runs (completed_at DESC);


-- -----------------------------------------------------------------------------
-- public.safety_findings — normalized probe outcomes (child of safety_runs)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.safety_findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES public.safety_runs(id) ON DELETE CASCADE,
    finding_key         TEXT NOT NULL,              -- SafetyFinding.id (UUID from merge)
    category            TEXT NOT NULL,              -- smoke | policy | jailbreak | leakage | toxicity
    source              TEXT NOT NULL,              -- garak | promptfoo | duke_probe
    passed              BOOLEAN NOT NULL,           -- true = model resisted the probe
    severity            TEXT NOT NULL,              -- low | medium | high | critical
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    probe_id            TEXT NOT NULL,
    probe_suite         TEXT,
    corroborated_by     JSONB,                      -- string array or null

    UNIQUE (run_id, finding_key)
);

CREATE INDEX IF NOT EXISTS idx_safety_findings_run_id ON public.safety_findings (run_id);
