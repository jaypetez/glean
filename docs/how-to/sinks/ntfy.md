---
title: "How to set up ntfy — glean"
description: "Send glean digests as push notifications through ntfy.sh or a self-hosted ntfy server."
---

# How to set up ntfy

**Goal:** Receive each feed digest as an ntfy push notification.

**You need:**

- A topic on [ntfy.sh](https://ntfy.sh) or a self-hosted ntfy server.
- The ntfy Android or iOS app, or a browser subscription.
- A token if your ntfy server requires authentication.

## Steps

1. Choose where to send notifications:

   - Public service: use `https://ntfy.sh`.
   - Self-hosted: use your server URL, such as `https://ntfy.example.com`.

2. Pick a private topic name. It must be 1 to 64 characters and use only letters, digits, `_`, or `-`.
3. Subscribe to that topic in the ntfy Android app, iOS app, or web UI.
4. If the topic is private, store the token in `.env`:

   ```dotenv
   NTFY_TOKEN_AI=<ntfy-access-token>
   ```

5. Add an ntfy sink to the feed:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: ntfy
           topic: glean_ai_news
           base_url: https://ntfy.sh
           token: ${NTFY_TOKEN_AI}
           priority: 3
           tags: [newspaper]
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

6. Remove `token` if you use a public topic with no auth.

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

If the topic contains a space, dot, or slash, validation fails before the daemon starts.

## Next steps

- [Set up a file sink for an archive copy](file.md)
- [ntfy sink reference](../../config/feeds.md#ntfy)
