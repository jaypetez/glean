---
title: "How to set up Telegram — glean"
description: "Send glean digests to a Telegram DM, group, or channel with the Bot API."
---

# How to set up Telegram

**Goal:** Send each feed digest to a Telegram DM, group, or channel.

**You need:**

- A Telegram account.
- A bot token from [@BotFather](https://t.me/BotFather).
- A DM, group, or channel where the bot can post.

## Steps

1. Open Telegram, message [@BotFather](https://t.me/BotFather), run `/newbot`, and copy the bot token.
2. Put the token in `.env` so it is not committed:

   ```dotenv
   TELEGRAM_BOT_TOKEN=<bot-token-from-botfather>
   TELEGRAM_CHAT_AI=<chat-id-from-getUpdates>
   ```

3. Get the chat ID:

   - **DM:** Send any message to your bot, then open `https://api.telegram.org/bot<token>/getUpdates` and copy `message.chat.id`.
   - **Group:** Add the bot to the group, send a message in the group, then copy the negative `message.chat.id`.
   - **Channel:** Add the bot as an admin. For a public channel, use `@channelusername`; for a private channel, post once and copy the negative `channel_post.chat.id` from `/getUpdates`.

4. Add a Telegram sink to the feed:

   ```yaml
   feeds:
     - name: ai-news
       schedule: "every 1h"
       sinks:
         - type: telegram
           chat_id: ${TELEGRAM_CHAT_AI}
       sources:
         - type: rss
           url: https://example.com/feed.xml
       pipeline:
         - dedup
         - summarize
         - digest
   ```

5. Choose one Telegram render style:

   ```yaml
   render:
     style: html        # bold titles, italic source, links; default
   ```

   ```yaml
   render:
     style: markdown_v2 # Telegram MarkdownV2 escaping
   ```

   ```yaml
   render:
     style: plain       # no markup
   ```

6. Leave `link_preview` unset unless you want Telegram previews; the default is `false`.

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

## Next steps

- [Set up fanout to send the same feed to multiple sinks](fanout.md)
- [Telegram sink reference](../../config/feeds.md#telegram)
