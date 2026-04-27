-- Migration 010: Performance indexes on existing tables
-- Speeds up the most common queries across all V2 pages.

-- companies
CREATE INDEX IF NOT EXISTS idx_companies_active   ON companies(is_active);
CREATE INDEX IF NOT EXISTS idx_companies_source   ON companies(source);
CREATE INDEX IF NOT EXISTS idx_companies_ats_type ON companies(ats_type);
CREATE INDEX IF NOT EXISTS idx_companies_name     ON companies(name);

-- jobs
CREATE INDEX IF NOT EXISTS idx_jobs_match_score   ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered_at ON jobs(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company       ON jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_jobs_user_action   ON jobs(user_action);
CREATE INDEX IF NOT EXISTS idx_jobs_is_new        ON jobs(is_new);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen     ON jobs(last_seen_at DESC);

-- fingerprint lookup — the dedup hot path
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_fingerprint ON jobs(fingerprint)
  WHERE fingerprint IS NOT NULL;

-- signals
CREATE INDEX IF NOT EXISTS idx_signals_unprocessed ON signals(processed)
  WHERE processed = false;
CREATE INDEX IF NOT EXISTS idx_signals_company     ON signals(company_id);
