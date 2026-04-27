-- Migration 004: Create job_sources table
-- Replaces the source_boards comma-separated string anti-pattern.
-- One row per (job × board) sighting. Existing source_boards column kept for V1 compat.

CREATE TABLE IF NOT EXISTS job_sources (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id       uuid        NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  source_board text        NOT NULL,
  source_url   text,
  raw_payload  jsonb,
  seen_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_job_sources_job   ON job_sources(job_id);
CREATE INDEX IF NOT EXISTS idx_job_sources_board ON job_sources(source_board, seen_at DESC);

-- Backfill: explode existing source_boards CSV into rows
INSERT INTO job_sources (job_id, source_board, seen_at)
SELECT
  j.id,
  trim(b.board),
  COALESCE(j.discovered_at, now())
FROM jobs j,
     unnest(string_to_array(j.source_boards, ',')) AS b(board)
WHERE j.source_boards IS NOT NULL
  AND j.source_boards <> ''
  AND trim(b.board) <> '';
