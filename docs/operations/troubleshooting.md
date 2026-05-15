---
title: "Troubleshooting — glean Operations"
description: Symptoms, causes, and fixes for common glean runtime problems.
---

# Troubleshooting

## "TELEGRAM_BOT_TOKEN is not set"

Your `.env` either isn't being loaded or doesn't have the var. With docker-compose, the `env_file:` directive loads `.env` from the same directory as `docker-compose.yml`. Run `docker compose config` to see what got loaded.

## Bot is in the group but messages never arrive

1. **Privacy mode.** New bots have it on by default. Talk to `@BotFather`, pick your bot, `Bot Settings → Group Privacy → Turn off`. Re-add the bot to the group.
2. **Wrong chat_id.** Group chat IDs are negative integers (often `-100...`). Send a message in the group, then GET `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `chat.id`.
3. **Feed is in bootstrap mode.** First run of a new feed indexes silently. Check `glean list-feeds` — if it says `pre-bootstrap`, the next tick will bootstrap; the *one after that* sends.

## "no new items" every tick

Likely the feed's source isn't returning anything fresh, or every item is already in `seen_items`. Run `glean test-feed <name>` — it shows fetched count without sending.

<a id="reset-a-stuck-feed"></a>
To start over for one feed, use the dedicated [reset one feed how-to](../how-to/ops/reset-feed.md).

## Ollama: "model not found"

You haven't pulled the model into the container's volume yet:

```sh
docker exec -it glean-ollama ollama pull qwen2.5:7b
```

Available models: `https://ollama.com/library`.

## Anthropic / OpenAI: "API key is not set"

Add `ANTHROPIC_API_KEY=...` / `OPENAI_API_KEY=...` to `.env`. The key is read at provider construction time — restart the container after editing `.env`.

## Schedules in the wrong timezone

`daily 09:00` uses `$TZ`. Set `TZ=America/Los_Angeles` (or whatever IANA zone) in `.env`. Default is UTC.

## Telegram "Bad Request: can't parse entities"

You're hitting an HTML / MarkdownV2 escape edge case. Set the feed's `render.style: plain` temporarily to confirm content goes through, then file an issue with the offending item.

## I want to reset everything

```sh
docker compose down
rm -rf ./data
docker compose up -d
```

This nukes `seen_items`, all feed state, and ETag cache. Next run bootstraps every feed silently.

## Where are the logs?

`docker compose logs -f glean`. Set `LOG_LEVEL=DEBUG` for more, `LOG_FORMAT=json` for machine-readable.
