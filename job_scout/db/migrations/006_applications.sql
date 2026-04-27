-- Migration 006: Create applications + application_events tables
-- Replaces user_action / applied_date / follow_up_date flat columns on jobs.
-- Old columns kept intact for V1 backward compatibility.

CREATE TABLE IF NOT EXISTS applications (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id           uuid        NOT NULL REFERENCES jobs(id),
  status           text        NOT NULL DEFAULT 'saved',
  applied_via      text,
  cover_letter     text,
  applied_at       timestamptz,
  follow_up_due_at timestamptz,
  responded_at     timestamptz,
  interview_at     timestamptz,
  closed_at        timestamptz,
  notes            text,
  created_at       timestamptz DEFAULT now(),
  updated_at       timestamptz DEFAULT now(),
  CONSTRAINT applications_job_unique UNIQUE (job_id)
);

CREATE INDEX IF NOT EXISTS idx_applications_status    ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON applications(follow_up_due_at)
  WHERE follow_up_due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS application_events (
  id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id uuid        NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  event_type     text        NOT NULL,
  occurred_at    timestamptz DEFAULT now(),
  metadata       jsonb,
  created_by     text        DEFAULT 'user'
);

CREATE INDEX IF NOT EXISTS idx_app_events_application ON application_events(application_id);

-- Backfill: migrate existing user_action rows into applications
INSERT INTO applications (job_id, status, applied_via, cover_letter, applied_at, follow_up_due_at, notes, created_at)
SELECT
  id,
  CASE user_action
    WHEN 'applied'     THEN 'applied'
    WHEN 'saved'       THEN 'saved'
    WHEN 'rejected'    THEN 'rejected'
    WHEN 'responded'   THEN 'responded'
    WHEN 'interview'   THEN 'interviewing'
    WHEN 'interviewing' THEN 'interviewing'
    ELSE 'saved'
  END,
  'manual',
  cover_letter_snippet,
  applied_date,
  follow_up_date,
  NULL,
  COALESCE(discovered_at, now())
FROM jobs
WHERE user_action IS NOT NULL
ON CONFLICT (job_id) DO NOTHING;
