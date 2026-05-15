-- depends:
-- 0001_initial: bootstrap glean state schema

CREATE TABLE IF NOT EXISTS seen_items (
  feed         TEXT NOT NULL,
  item_hash    TEXT NOT NULL,
  url          TEXT,
  seen_at      INTEGER NOT NULL,
  sent         INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (feed, item_hash)
);

CREATE INDEX IF NOT EXISTS idx_seen_items_feed_seen_at ON seen_items(feed, seen_at);

CREATE TABLE IF NOT EXISTS feed_runs (
  feed                  TEXT PRIMARY KEY,
  last_success_at       INTEGER,
  last_attempt_at       INTEGER,
  last_error            TEXT,
  consecutive_failures  INTEGER NOT NULL DEFAULT 0,
  alert_active          INTEGER NOT NULL DEFAULT 0,
  bootstrapped          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS etag_cache (
  url           TEXT PRIMARY KEY,
  etag          TEXT,
  last_modified TEXT,
  cached_at     INTEGER
);
