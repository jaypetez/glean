-- depends: 0002_digests

CREATE TABLE IF NOT EXISTS feed_run_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feed_name TEXT NOT NULL,
  started_at TIMESTAMP NOT NULL,
  duration_ms INTEGER NOT NULL,
  status TEXT NOT NULL,
  fetched INTEGER NOT NULL DEFAULT 0,
  after_dedup INTEGER NOT NULL DEFAULT 0,
  dropped INTEGER NOT NULL DEFAULT 0,
  sent INTEGER NOT NULL DEFAULT 0,
  overflow INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  trace_id TEXT,
  dry_run INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_feed_run_history_feed_started
  ON feed_run_history(feed_name, started_at DESC);
