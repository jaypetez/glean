-- depends: 0001_initial

CREATE TABLE IF NOT EXISTS digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feed_name TEXT NOT NULL,
  sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  style TEXT NOT NULL,
  intro TEXT,
  body TEXT NOT NULL,
  fragment_index INTEGER NOT NULL DEFAULT 0,
  item_count INTEGER NOT NULL DEFAULT 0,
  trace_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_digests_feed_sent ON digests(feed_name, sent_at DESC);
