-- =============================================================================
-- Auth + run visibility — users, links, pillar column additions
-- =============================================================================
-- Target database: qa_ai_models   Target schema: public
--
-- Apply: uv run python -m dbutils.apply_schema db/auth_schema.sql
-- Backfill: uv run python db/migrate_auth_columns.py --apply
-- =============================================================================

-- -----------------------------------------------------------------------------
-- public.users — upserted on first OIDC login
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    netid           TEXT NOT NULL UNIQUE,
    email           TEXT,
    display_name    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_netid ON public.users (netid);


-- -----------------------------------------------------------------------------
-- public.user_run_links — associate users with canonical runs (reuse / owner)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.user_run_links (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    pillar          TEXT NOT NULL CHECK (pillar IN ('scan', 'safety', 'eval', 'benchmark')),
    run_id          UUID NOT NULL,
    link_type       TEXT NOT NULL DEFAULT 'reused' CHECK (link_type IN ('owner', 'reused')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (user_id, pillar, run_id)
);

CREATE INDEX IF NOT EXISTS idx_user_run_links_user_pillar
    ON public.user_run_links (user_id, pillar);


-- -----------------------------------------------------------------------------
-- Additive columns on pillar run tables (idempotent ALTER)
-- -----------------------------------------------------------------------------

ALTER TABLE public.scans ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public';
ALTER TABLE public.scans ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES public.users(id);
ALTER TABLE public.scans ADD COLUMN IF NOT EXISTS config_fingerprint TEXT;
ALTER TABLE public.scans ADD COLUMN IF NOT EXISTS config_json JSONB;

ALTER TABLE public.safety_runs ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public';
ALTER TABLE public.safety_runs ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES public.users(id);
ALTER TABLE public.safety_runs ADD COLUMN IF NOT EXISTS config_fingerprint TEXT;
ALTER TABLE public.safety_runs ADD COLUMN IF NOT EXISTS config_json JSONB;

ALTER TABLE public.eval_runs ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public';
ALTER TABLE public.eval_runs ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES public.users(id);
ALTER TABLE public.eval_runs ADD COLUMN IF NOT EXISTS config_fingerprint TEXT;
ALTER TABLE public.eval_runs ADD COLUMN IF NOT EXISTS config_json JSONB;

ALTER TABLE public.benchmark_runs ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'public';
ALTER TABLE public.benchmark_runs ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES public.users(id);
ALTER TABLE public.benchmark_runs ADD COLUMN IF NOT EXISTS config_fingerprint TEXT;
ALTER TABLE public.benchmark_runs ADD COLUMN IF NOT EXISTS config_json JSONB;

-- Partial unique indexes for run deduplication (complete runs only)
CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_public_fingerprint
    ON public.scans (config_fingerprint)
    WHERE visibility = 'public' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_scans_private_fingerprint_owner
    ON public.scans (config_fingerprint, owner_user_id)
    WHERE visibility = 'private' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_safety_runs_public_fingerprint
    ON public.safety_runs (config_fingerprint)
    WHERE visibility = 'public' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_safety_runs_private_fingerprint_owner
    ON public.safety_runs (config_fingerprint, owner_user_id)
    WHERE visibility = 'private' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_runs_public_fingerprint
    ON public.eval_runs (config_fingerprint)
    WHERE visibility = 'public' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_runs_private_fingerprint_owner
    ON public.eval_runs (config_fingerprint, owner_user_id)
    WHERE visibility = 'private' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmark_runs_public_fingerprint
    ON public.benchmark_runs (config_fingerprint)
    WHERE visibility = 'public' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmark_runs_private_fingerprint_owner
    ON public.benchmark_runs (config_fingerprint, owner_user_id)
    WHERE visibility = 'private' AND status = 'complete' AND config_fingerprint IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_scans_visibility ON public.scans (visibility);
CREATE INDEX IF NOT EXISTS idx_safety_runs_visibility ON public.safety_runs (visibility);
CREATE INDEX IF NOT EXISTS idx_eval_runs_visibility ON public.eval_runs (visibility);
CREATE INDEX IF NOT EXISTS idx_benchmark_runs_visibility ON public.benchmark_runs (visibility);
