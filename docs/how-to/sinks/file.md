---
title: "How to set up a file sink — glean"
description: "Append glean digests to text, JSON Lines, or Markdown files."
---

# How to set up a file sink

**Goal:** Keep an append-only local archive of feed digests.

**You need:**

- A writable directory mounted into the glean container.
- A target path under an allowed file sink root.
- A format choice: `text`, `jsonl`, or `markdown`.

## Steps

1. Pick an allowed root. By default, file sink paths must resolve under `/data/` or `/tmp/glean/` inside the container.
2. If you need another root, set `GLEAN_FILE_SINK_ROOTS` in `.env`:

   ```dotenv
   GLEAN_FILE_SINK_ROOTS=/data,/archive
   ```

3. Add a file sink to the feed:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: file
           path: /data/archives/ai-news.jsonl
           format: jsonl
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

4. Choose one format:

   ```yaml
   format: text     # rendered digest chunks separated by dividers
   ```

   ```yaml
   format: jsonl    # one JSON object per item
   ```

   ```yaml
   format: markdown # heading, summary, link, source
   ```

5. Keep the file path below the allowed root; deeply nested paths with more than 10 segments are rejected.
6. Treat writes as append-only. During normal scheduled runs, glean dedupes already-seen items before the sink runs, so repeated ticks do not append the same items again.

## Verify

Run:

```bash
uv run glean validate-config -c feeds.yaml
```

Expected output includes:

```text
OK — 1 feed(s)
  - ai-news: schedule='every 1h' sources=1
```

If the path is outside the allowlist, validation fails before the daemon starts.

## Next steps

- [Set up fanout to send to Telegram and keep a file archive](fanout.md)
- [File sink reference](../../config/feeds.md#file)
