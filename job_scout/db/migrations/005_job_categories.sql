-- Migration 005: Create job_categories table
-- Multi-label classification per job.
-- Categories: desperation, startup, funding, hidden_gem, regional, yc, asap, salary_transparent

CREATE TABLE IF NOT EXISTS job_categories (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id      uuid        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  category    text        NOT NULL,
  confidence  numeric     DEFAULT 1.0,
  assigned_at timestamptz DEFAULT now(),
  CONSTRAINT job_category_unique UNIQUE (job_id, category)
);

CREATE INDEX IF NOT EXISTS idx_job_categories_job      ON job_categories(job_id);
CREATE INDEX IF NOT EXISTS idx_job_categories_category ON job_categories(category);

-- Backfill: seed desperation category from existing desperation_score
INSERT INTO job_categories (job_id, category, confidence, assigned_at)
SELECT
  id,
  'desperation',
  LEAST(desperation_score::numeric / 100, 1.0),
  COALESCE(discovered_at, now())
FROM jobs
WHERE desperation_score IS NOT NULL AND desperation_score >= 30
ON CONFLICT (job_id, category) DO NOTHING;

-- Backfill: seed recommended category from existing is_recommended flag
INSERT INTO job_categories (job_id, category, confidence, assigned_at)
SELECT
  id,
  'recommended',
  1.0,
  COALESCE(discovered_at, now())
FROM jobs
WHERE is_recommended = true
ON CONFLICT (job_id, category) DO NOTHING;
