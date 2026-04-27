-- Migration 009: Infrastructure tables
-- api_usage: DB-backed quota tracking (replaces broken JSON files in Docker)
-- sources_config: per-source enable/disable + config overrides
-- custom_queries: saved Serper dorks with optional daily-run inclusion

CREATE TABLE IF NOT EXISTS api_usage (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  provider     text        NOT NULL,
  period_key   text        NOT NULL,
  count        integer     DEFAULT 0,
  last_call_at timestamptz,
  CONSTRAINT api_usage_unique UNIQUE (provider, period_key)
);

CREATE INDEX IF NOT EXISTS idx_api_usage_period ON api_usage(provider, period_key);

CREATE TABLE IF NOT EXISTS sources_config (
  id           uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name  text    NOT NULL,
  source_type  text,
  is_enabled   boolean DEFAULT true,
  config       jsonb,
  CONSTRAINT sources_config_unique UNIQUE (source_name)
);

CREATE TABLE IF NOT EXISTS custom_queries (
  id                   uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name                 text        NOT NULL,
  query                text        NOT NULL,
  category             text,
  is_active            boolean     DEFAULT true,
  include_in_daily_run boolean     DEFAULT false,
  created_at           timestamptz DEFAULT now(),
  last_run_at          timestamptz
);
