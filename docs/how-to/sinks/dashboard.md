---
title: "Dashboard sink — glean"
description: Browse rendered digests in the built-in glean web UI.
---

# Dashboard sink

The `dashboard` sink persists every rendered digest fragment to glean's SQLite state DB so you can browse them in the built-in web UI at `http://127.0.0.1:9090/digests`.

## When to use

Use `dashboard` when you want a built-in digest viewer without wiring up Telegram, Discord, Slack, ntfy, or a webhook first. It works well for local development, first-run evaluation, demos, and small self-hosted setups that want a rolling in-app history. You can also pair it with delivery sinks when you want both live notifications and a recent on-box archive.

## Configuration

```yaml
sinks:
  - type: dashboard
    keep_last_n: 50      # optional; default 50; per-feed cap
    required: true       # optional; default true; if false, DB errors don't fail the feed
```

## Fields

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `keep_last_n` | int >= 1 | 50 | Per-feed retention. The 51st digest evicts the oldest. |
| `required` | bool | true | When `false`, a DB write failure logs a warning but doesn't fail the feed run. |

## Viewing digests

1. Start glean:

   ```bash
   docker compose up -d
   ```

2. Open `http://127.0.0.1:9090/` in a browser and authenticate with your `X-Glean-Api-Key`; the SPA stores and sends it for you after sign-in.
3. Click the **Digests** tab.
4. Filter by feed with the dropdown. Click any row to expand the full rendered body.
5. New digests appear automatically over the live SSE stream, so the list updates without a manual refresh.

## API access

The same data is available programmatically:

- `GET /api/v1/digests?limit=50&before=<id>` — cross-feed
- `GET /api/v1/feeds/{name}/digests?limit=50&before=<id>` — per-feed

Both endpoints require the `X-Glean-Api-Key` header.

## Retention semantics

Retention is enforced per feed, not globally. Each write trims that feed back to `keep_last_n` in oldest-first order, so a cap of `50` keeps the 50 most recent rendered digest fragments for that feed and evicts the oldest entry when the next one arrives. Insert and trim happen in the same DB transaction, so you do not get transient over-retention or cross-feed interference.

## Security

The stored body is the same rendered digest glean already produced for delivery. By the time it reaches the `dashboard` sink, summarizer output has passed through `glean.llm.output_filter`, and sink rendering has applied the same escaping rules the engine uses for delivery. The web UI renders HTML-style digests through Svelte's escaped HTML handling; `plain` and `markdown_v2` outputs are shown as text-oriented content rather than reinterpreted as raw HTML.

## See also

- [File sink](file.md) — archive to JSONL/markdown
- [Webhook sink](webhook.md) — POST to any URL
