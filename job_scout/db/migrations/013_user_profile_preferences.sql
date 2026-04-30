-- Migration 013: Add preferences JSONB column to user_profile
-- This column stores search criteria (title_keywords, skills, exclude_keywords,
-- remote_only, global_remote, max_yoe, min_salary) set from the Discovery and
-- Profile pages, used by the pipeline for scoring and filtering.

ALTER TABLE user_profile
  ADD COLUMN IF NOT EXISTS preferences jsonb DEFAULT '{}';

-- Backfill existing rows with empty preferences object
UPDATE user_profile SET preferences = '{}' WHERE preferences IS NULL;
