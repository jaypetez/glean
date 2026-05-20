-- depends: 0003_feed_run_history

ALTER TABLE seen_items ADD COLUMN title TEXT;
ALTER TABLE seen_items ADD COLUMN sent_at INTEGER;
ALTER TABLE seen_items ADD COLUMN embedding BLOB;
ALTER TABLE seen_items ADD COLUMN embedding_model TEXT;

UPDATE seen_items
SET sent_at = seen_at
WHERE sent = 1 AND sent_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_seen_items_feed_sent
  ON seen_items(feed, sent_at DESC) WHERE sent_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS semantic_dedup_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feed_name TEXT NOT NULL,
  suppressed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  suppressed_url TEXT NOT NULL,
  suppressed_title TEXT,
  matched_url TEXT NOT NULL,
  matched_title TEXT,
  similarity REAL NOT NULL,
  trace_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_semantic_dedup_log_feed_at
  ON semantic_dedup_log(feed_name, suppressed_at DESC);
