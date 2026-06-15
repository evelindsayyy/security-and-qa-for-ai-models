-- =============================================================================
-- Efficacy pillar — PostgreSQL schema (PROPOSAL, not yet applied)
-- =============================================================================
-- Target database: qa_ai_models   Target schema: public
--
-- Status: DRAFT for team review. Running this file CREATEs tables in the
-- shared Duke Postgres (codeplus-postgres-test-01). DO NOT run it until:
--   1. The team confirms the efficacy tables belong in `public` and nobody
--      else is mid-migration of the same tables.
--   2. Someone with CREATE rights on `public` reviews this.
--
-- Design sources:
--   - docs/data-model.md  — the team's target table sketch (Track B section);
--     it puts all tables in `public`, which is what this file targets.
--   - evaluator/schemas.py — the actual EvaluationResult shape on disk
--
-- Shape decision: OPTION A (one row in eval_results per QUESTION, with the
-- per-dimension judge scores stored in the `detail` JSONB). This mirrors the
-- evaluator/results/*.jsonl files 1:1 — each JSONL line becomes one
-- eval_results row — so the loader and the frontend port with minimal logic.
-- (Option B, one row per question*dimension, was the alternative; rejected
-- for now to stay close to the file shape. A per-dimension VIEW can be added
-- later if cross-model per-dimension SQL queries are needed.)
--
-- Difference from docs/data-model.md, on purpose:
--   - eval_runs carries a `judge_model` column and an `adaptation` JSONB —
--     the doc predates the LLM-as-judge + multi-dimension rubric work.
-- =============================================================================

-- gen_random_uuid() is built into Postgres 13+. If this errors, the server is
-- older and needs:  CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- (No CREATE SCHEMA needed — `public` exists in every database by default.)


-- -----------------------------------------------------------------------------
-- public.task_suites — one row per (question set, version)
-- -----------------------------------------------------------------------------
-- Parent of eval_runs. So far we'd have two rows: it_support v1, policy_qa v1.
-- A "suite" is the locked set of questions + the rubric used to score them.

CREATE TABLE IF NOT EXISTS public.task_suites (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suite_key       TEXT NOT NULL,            -- 'it_support', 'policy_qa'
    version         TEXT NOT NULL,            -- 'v1' (from task_suite_version suffix)
    yaml_path       TEXT,                     -- 'tasks/rubrics/it_support.yaml'
    rubric_version  TEXT,                     -- 'it_support_v1', 'policy_qa_v1'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A suite_key+version pair is unique: re-importing the same suite must not
    -- create a duplicate. The loader uses this for ON CONFLICT idempotency.
    UNIQUE (suite_key, version)
);


-- -----------------------------------------------------------------------------
-- public.eval_runs — one row per RUN (one results JSONL file)
-- -----------------------------------------------------------------------------
-- A run = one candidate model evaluated on one suite by one judge. The
-- run-level aggregates (mean score, total cost, total tokens) are precomputed
-- here so the dashboard reads them directly instead of re-aggregating files.

CREATE TABLE IF NOT EXISTS public.eval_runs (
    -- Reuse the evaluation_run_id from the JSONL (already a uuid4). Making it
    -- the PK gives the loader free idempotency: ON CONFLICT (id) DO NOTHING.
    id                  UUID PRIMARY KEY,
    suite_id            UUID NOT NULL REFERENCES public.task_suites(id),

    gateway_model_id    TEXT NOT NULL,        -- adaptation.candidate_model
    judge_model         TEXT,                 -- adaptation.judge_model
    status              TEXT NOT NULL DEFAULT 'complete',

    -- Aggregates (computed from the file's rows at load time).
    aggregate_score     DOUBLE PRECISION,     -- mean of per-question `overall`
    latency_p50_ms      INTEGER,
    latency_p95_ms      INTEGER,
    tokens_in_total     INTEGER,
    tokens_out_total    INTEGER,
    cost_usd_total      NUMERIC(12, 6),

    -- Full HOW-it-was-run metadata (temperature, max_tokens, prompt versions,
    -- rubric_version, judge_prompt_version). Kept as JSONB so the schema
    -- doesn't churn every time the Adaptation dataclass gains a field.
    adaptation          JSONB,
    tool_results        JSONB,                -- optional raw judge logs

    source_file         TEXT,                 -- the JSONL filename, for traceability
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_suite   ON public.eval_runs (suite_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_model   ON public.eval_runs (gateway_model_id);


-- -----------------------------------------------------------------------------
-- public.eval_results — one row per QUESTION in a run (Option A)
-- -----------------------------------------------------------------------------
-- Each row corresponds to one line in the results JSONL. The four (or five)
-- per-dimension judge scores + rationales live inside `detail`, not as columns,
-- so different rubrics with different dimensions all fit the same table.

CREATE TABLE IF NOT EXISTS public.eval_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_run_id     UUID NOT NULL REFERENCES public.eval_runs(id) ON DELETE CASCADE,

    task_id         TEXT NOT NULL,            -- question_id, e.g. 'it-support-001'
    metric          TEXT NOT NULL DEFAULT 'judge_score',  -- Option A: always 'judge_score'
    score           DOUBLE PRECISION,         -- the weighted `overall` (NULL if a dim failed)

    latency_ms      INTEGER,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    cost_usd        NUMERIC(12, 6),

    -- Failure flags carried over from the JSONL so failed questions are
    -- queryable, not silently dropped.
    candidate_failed BOOLEAN NOT NULL DEFAULT false,
    judge_failed     BOOLEAN NOT NULL DEFAULT false,

    -- Everything the UI drills into:
    --   {"candidate_response": "...",
    --    "scores": {"accuracy": {"score": 5, "rationale": "..."}, ...},
    --    "error": null,
    --    "schema_version": "1.0.0"}   -- the EvaluationResult contract version
    detail          JSONB,

    -- One result per (run, question, metric): re-importing a file must not
    -- duplicate rows. The loader uses this for ON CONFLICT idempotency.
    UNIQUE (eval_run_id, task_id, metric)
);

CREATE INDEX IF NOT EXISTS idx_eval_results_run  ON public.eval_results (eval_run_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_task ON public.eval_results (task_id);


-- =============================================================================
-- Notes for review
-- =============================================================================
-- 1. `models` table (the gateway catalog anchor in data-model.md) is shared
--    across pillars and is NOT created here — its ownership is a cross-team
--    decision. eval_runs references the model by its string id
--    (gateway_model_id) for now; a FK to a real models table can be added
--    once that table exists in public.
-- 2. All money columns are NUMERIC(12,6) (exact) not float — never store
--    currency as floating point.
-- 3. Timestamps are TIMESTAMPTZ (timezone-aware). The JSONL timestamps are
--    UTC ISO-8601, which map cleanly.
-- 4. To undo everything this created (review/testing only):
--      DROP TABLE IF EXISTS public.eval_results, public.eval_runs, public.task_suites CASCADE;
-- =============================================================================
