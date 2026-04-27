-- Migration 007: Create resumes table
-- Versioned resume storage. Tailored resumes reference a base resume.
-- Backfills existing resume_text from user_profile as version 1 base.

CREATE TABLE IF NOT EXISTS resumes (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  version               integer     NOT NULL DEFAULT 1,
  is_base               boolean     DEFAULT false,
  base_resume_id        uuid        REFERENCES resumes(id),
  generated_for_job_id  uuid        REFERENCES jobs(id),
  content               text        NOT NULL,
  content_html          text,
  created_at            timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_resumes_base    ON resumes(is_base) WHERE is_base = true;
CREATE INDEX IF NOT EXISTS idx_resumes_version ON resumes(version DESC);

-- Backfill from user_profile if resume_text exists
INSERT INTO resumes (version, is_base, content, created_at)
SELECT 1, true, resume_text, now()
FROM user_profile
WHERE resume_text IS NOT NULL AND trim(resume_text) <> '';
