-- App-owned writeback table. The synced tables (users, user_scores,
-- recommendations) are created by `databricks postgres create-synced-table` in
-- bootstrap.sh; do NOT define them here.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS user_actions (
  action_id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            text        NOT NULL,
  recommendation_id  text,
  decision           text        NOT NULL CHECK (decision IN ('accepted', 'dismissed', 'snoozed')),
  notes              text,
  operator           text        NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS user_actions_created_at_idx ON user_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS user_actions_user_id_idx    ON user_actions (user_id);
