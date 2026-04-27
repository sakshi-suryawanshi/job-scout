-- Migration 003: Add V2 columns to jobs
-- Additive only — existing 484 rows untouched.

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS is_remote_global  boolean      DEFAULT false,
  ADD COLUMN IF NOT EXISTS last_seen_at      timestamptz  DEFAULT now(),
  ADD COLUMN IF NOT EXISTS salary_min        integer,
  ADD COLUMN IF NOT EXISTS salary_max        integer,
  ADD COLUMN IF NOT EXISTS application_notes text;

-- Backfill last_seen_at from discovered_at for existing rows
UPDATE jobs
SET last_seen_at = COALESCE(discovered_at, now())
WHERE last_seen_at IS NULL OR last_seen_at = now();
