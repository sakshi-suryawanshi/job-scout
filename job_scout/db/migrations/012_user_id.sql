-- Migration 012: Add user_id to all tables for multi-user-ready schema
--
-- V2_PLAN decision: "Single-user for now, multi-user-ready schema.
-- user_id FK on every table even though there's only one user. Cheap insurance."
--
-- Since there is no auth system yet, user_id defaults to a fixed UUID
-- representing the single user. When auth is added, rows can be scoped by
-- the real authenticated user_id without schema changes.

DO $$
BEGIN
    -- Add to companies
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='companies' AND column_name='user_id') THEN
        ALTER TABLE companies ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to jobs
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='jobs' AND column_name='user_id') THEN
        ALTER TABLE jobs ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to applications
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='applications' AND column_name='user_id') THEN
        ALTER TABLE applications ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to signals
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='signals' AND column_name='user_id') THEN
        ALTER TABLE signals ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to user_profile (this is inherently single-row per user)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='user_profile' AND column_name='user_id') THEN
        ALTER TABLE user_profile ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to pipeline_runs
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='pipeline_runs' AND column_name='user_id') THEN
        ALTER TABLE pipeline_runs ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to auto_apply_rules
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='auto_apply_rules' AND column_name='user_id') THEN
        ALTER TABLE auto_apply_rules ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;

    -- Add to job_categories
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='job_categories' AND column_name='user_id') THEN
        ALTER TABLE job_categories ADD COLUMN user_id uuid DEFAULT '00000000-0000-0000-0000-000000000001';
    END IF;
END $$;

-- Indexes for when multi-user filtering is needed
CREATE INDEX IF NOT EXISTS idx_companies_user_id    ON companies(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id         ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_applications_user_id ON applications(user_id);
CREATE INDEX IF NOT EXISTS idx_signals_user_id      ON signals(user_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_user_id ON pipeline_runs(user_id);
