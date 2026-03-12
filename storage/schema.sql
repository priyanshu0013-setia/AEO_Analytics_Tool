-- SQLite schema for the Mini AEO Analytics prototype
-- Focus: reproducibility and auditability.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  app_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,

  target_input_raw TEXT NOT NULL,
  target_input_normalized TEXT NOT NULL,
  target_final_url TEXT,
  target_registrable_domain TEXT NOT NULL,
  target_redirect_chain_json TEXT,

  competitors_input_raw TEXT NOT NULL,
  settings_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS query_variants (
  variant_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  seed_query TEXT NOT NULL,
  variant_text TEXT NOT NULL,
  variant_method TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS llm_responses (
  response_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  variant_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model_id TEXT NOT NULL,
  model_version TEXT,

  request_params_json TEXT NOT NULL,
  status TEXT NOT NULL, -- ok | blocked | error | cached
  error_message TEXT,

  response_text TEXT,
  response_raw_json TEXT,

  latency_ms INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
  FOREIGN KEY(variant_id) REFERENCES query_variants(variant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS detections (
  detection_id TEXT PRIMARY KEY,
  response_id TEXT NOT NULL,
  brand_domain TEXT NOT NULL,
  mentioned_binary INTEGER NOT NULL, -- 0/1
  mention_type TEXT NOT NULL, -- domain | url
  matched_snippet TEXT,
  rank_position INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY(response_id) REFERENCES llm_responses(response_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_variants_run ON query_variants(run_id);
CREATE INDEX IF NOT EXISTS idx_responses_run ON llm_responses(run_id);
CREATE INDEX IF NOT EXISTS idx_responses_variant ON llm_responses(variant_id);
CREATE INDEX IF NOT EXISTS idx_detections_response ON detections(response_id);
