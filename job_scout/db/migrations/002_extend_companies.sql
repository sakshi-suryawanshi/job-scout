-- Migration 002: Add V2 columns to companies
-- Additive only — existing 357 rows untouched.

ALTER TABLE companies
  ADD COLUMN IF NOT EXISTS slug          text,
  ADD COLUMN IF NOT EXISTS ats_slug      text,
  ADD COLUMN IF NOT EXISTS first_seen_at timestamptz DEFAULT now(),
  ADD COLUMN IF NOT EXISTS last_seen_at  timestamptz DEFAULT now();

-- Backfill first_seen_at / last_seen_at from created_at for existing rows
UPDATE companies
SET
  first_seen_at = created_at,
  last_seen_at  = COALESCE(last_scraped, created_at)
WHERE first_seen_at IS NULL OR first_seen_at = last_seen_at;
