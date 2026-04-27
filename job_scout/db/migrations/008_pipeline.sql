-- Migration 008: Create pipeline tables + auto-apply rules
-- Powers the Auto-Pilot page: scheduled daily run, stage tracking, rule-based auto-apply.

CREATE TABLE IF NOT EXISTS auto_apply_rules (
  id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text        NOT NULL,
  is_active  boolean     DEFAULT true,
  priority   integer     DEFAULT 0,
  conditions jsonb       NOT NULL DEFAULT '{}',
  action     jsonb       NOT NULL DEFAULT '{}',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  triggered_by text        DEFAULT 'manual',
  started_at   timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  status       text        DEFAULT 'running',
  stats        jsonb,
  digest_html  text,
  error_log    text
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS pipeline_stage_results (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       uuid        NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
  stage_name   text        NOT NULL,
  started_at   timestamptz,
  completed_at timestamptz,
  status       text,
  stats        jsonb,
  error        text
);

CREATE INDEX IF NOT EXISTS idx_pipeline_stages_run ON pipeline_stage_results(run_id);
