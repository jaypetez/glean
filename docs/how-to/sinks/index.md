---
title: "Sinks — glean How-to"
description: How to browse or deliver glean digests with the dashboard, email, Telegram, Discord, Slack, ntfy, webhooks, and files.
---

# Sink How-to Guides

Task-focused guides for browsing or delivering glean digests with built-in sink destinations.

- [Dashboard](dashboard.md) — Browse recent rendered digests in the built-in web UI.
- [Email (SMTP)](email.md) — Deliver digests as styled HTML email via any SMTP provider (Gmail, Fastmail, AWS SES, Mailgun, or self-hosted Mailpit).
- [Telegram](telegram.md) — Send digests to a Telegram DM, group, or channel.
- [Discord](discord.md) — Post digests to a Discord channel with a webhook.
- [Slack](slack.md) — Post digests to Slack with an incoming webhook.
- [ntfy](ntfy.md) — Send push notifications through ntfy.sh or a self-hosted server.
- [Webhook](webhook.md) — POST digest JSON to any HTTP endpoint.
- [File](file.md) — Append digests to text, JSON Lines, or Markdown archives.
- [Fanout](fanout.md) — Deliver one feed to multiple sinks in parallel.

See the [feeds.yaml sink reference](../../config/feeds.md#sinks) for all sink fields.
