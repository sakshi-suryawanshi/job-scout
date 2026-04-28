-- Migration 011: Create signals and user_profile tables
--
-- These tables were documented in 001_capture_v1_schema.sql as pre-existing V1
-- schema, but no CREATE TABLE statement was ever written.
-- A fresh Supabase project deployed from migrations would be missing them.
-- This migration makes the schema fully self-contained and reproducible.

-- ── signals ──────────────────────────────────────────────────────────────────
-- Stores discovery signals from Serper Dorking (distress, funding, hidden_gems,
-- regional). Written by db.add_signal(), read by the Signals viewer tab.

CREATE TABLE IF NOT EXISTS signals (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_type      text        NOT NULL,        -- distress | funding | hidden_gem | regional | ...
    confidence_score numeric     DEFAULT 0.5,
    source_signal    text,                        -- raw snippet / source URL
    metadata         jsonb       DEFAULT '{}',
    processed        boolean     DEFAULT false,
    company_id       uuid        REFERENCES companies(id) ON DELETE SET NULL,
    company_name     text,                        -- denormalised for fast display
    url              text,
    snippet          text,
    created_at       timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_signals_type       ON signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_signals_company_id ON signals(company_id);
CREATE INDEX IF NOT EXISTS idx_signals_created    ON signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_unprocessed ON signals(processed) WHERE processed = false;


-- ── user_profile ──────────────────────────────────────────────────────────────
-- Single-row table for the user's profile: resume text, AI-extracted summary,
-- skills, and search preferences. Written by Profile page, read everywhere.

CREATE TABLE IF NOT EXISTS user_profile (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_text      text,
    resume_summary   text,
    skills           text,           -- JSON-encoded list stored as text
    preferred_roles  text,           -- JSON-encoded list stored as text
    experience_years integer,
    preferences      jsonb DEFAULT '{}',   -- title_keywords, skills, exclude_keywords, etc.
    updated_at       timestamptz DEFAULT now()
);

-- Ensure there is always at most one profile row
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profile_singleton
    ON user_profile ((true));   -- unique on a constant expression → max 1 row
