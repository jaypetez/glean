---
title: "How to set up a webhook — glean"
description: "POST glean digests to any HTTP endpoint as JSON."
---

# How to set up a webhook

**Goal:** Send each feed digest to a generic HTTP endpoint.

**You need:**

- An HTTPS endpoint that accepts JSON.
- Any required bearer token, basic auth credentials, or custom headers.
- A secure place to store secrets, such as `.env`.

## Steps

1. Store endpoint secrets in `.env`:

   ```dotenv
   WEBHOOK_DIGEST_URL=<https-endpoint-url>
   WEBHOOK_TOKEN=<bearer-token>
   ```

2. Add a webhook sink to the feed:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: webhook
           url: ${WEBHOOK_DIGEST_URL}
           method: POST
           auth_bearer: ${WEBHOOK_TOKEN}
           headers:
             X-Glean-Feed: ai-news
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

3. Use only the allowed methods: `POST`, `PUT`, or `PATCH`.
4. Use `auth_bearer` to add `Authorization: Bearer <token>` automatically.
5. Use `headers` for extra static headers. If you need basic auth, set `auth_basic: [username, password]`.
6. Configure your receiver for this JSON payload:

   ```json
   {
     "feed": "ai-news",
     "intro": "AI news this hour",
     "messages": ["rendered digest chunk"],
     "items": [
       {
         "title": "Item title",
         "url": "https://example.com/item",
         "summary": "LLM summary",
         "source_type": "rss",
         "source_name": "Example feed",
         "published_at": "2025-01-01T12:00:00+00:00",
         "score": 0.8,
         "relevance": 0.9
       }
     ]
   }
   ```

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

If `method` is `GET` or `DELETE`, validation fails before the daemon starts.

## Next steps

- [Set up fanout to send to the webhook and another sink](fanout.md)
- [Webhook sink reference](../../config/feeds.md#webhook)
