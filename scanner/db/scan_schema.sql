-- =============================================================================
-- Scanner pillar — PostgreSQL schema (PROPOSAL, not yet applied)
-- =============================================================================
-- Target database: qa_ai_models   Target schema: public
--
-- Status: DRAFT for team review. Running this file CREATEs tables in the
-- shared Duke Postgres (codeplus-postgres-test-01). DO NOT run until someone
-- with CREATE rights on `public` has reviewed this.
--
-- Design sources:
--   - docs/data-model.md  — scans / findings table sketch (Track A)
--   - scanner/schemas.py  — ScanResult + Finding on disk
--
-- Idempotency keys (loader ON CONFLICT DO NOTHING):
--   scans:     UNIQUE (hf_repo, completed_at)  — completed_at = scan_metadata.scanned_at
--   findings:  UNIQUE (scan_id, finding_key)    — finding_key = Finding.id (16-char hex)
--
-- Deferred: shared `models` table FK on scans.model_id (same stance as eval_runs).
-- =============================================================================

-- gen_random_uuid() is built into Postgres 13+. If this errors, the server is
-- older and needs:  CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- -----------------------------------------------------------------------------
-- public.scans — one HF artifact inspection job (one scan_result.json load)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.scans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id            UUID,                   -- nullable; FK to models.id when that table exists
    hf_repo             TEXT NOT NULL,          -- ScanResult.model_id (e.g. gpt2, org/model)
    status              TEXT NOT NULL DEFAULT 'complete',
    overall_risk_score  INTEGER NOT NULL DEFAULT 0,
    severity_tier       TEXT NOT NULL,          -- low | medium | high | critical
    scanned_files       JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_results        JSONB NOT NULL DEFAULT '{}'::jsonb,
    scan_metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,            -- scan_metadata.scanned_at (idempotency key)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (hf_repo, completed_at)
);

CREATE INDEX IF NOT EXISTS idx_scans_hf_repo ON public.scans (hf_repo);
CREATE INDEX IF NOT EXISTS idx_scans_completed_at ON public.scans (completed_at DESC);


-- -----------------------------------------------------------------------------
-- public.findings — normalized actionable issues (child of scans)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id             UUID NOT NULL REFERENCES public.scans(id) ON DELETE CASCADE,
    finding_key         TEXT NOT NULL,          -- deterministic Finding.id from JSON
    source              TEXT NOT NULL,          -- modelscan | fickling | modelaudit | pip_audit | osv | trufflehog
    title               TEXT NOT NULL,
    severity            TEXT NOT NULL,
    file_path           TEXT,
    description         TEXT NOT NULL DEFAULT '',
    raw_tool_severity   TEXT,
    remediation         TEXT,
    corroborated_by     JSONB,                  -- string array from JSON

    UNIQUE (scan_id, finding_key)
);

CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON public.findings (scan_id);
