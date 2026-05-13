# Quickstart

## 1. Get a Telegram bot token

Message [@BotFather](https://t.me/BotFather) on Telegram and create a new bot. Add the bot to a group, then get the chat ID by sending a message and visiting:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

## 2. Configure

```bash
cp .env.example .env
cp feeds.example.yaml feeds.yaml
```

Edit `.env` with your bot token and chat IDs. Edit `feeds.yaml` to define your feeds.

## 3. Run

```bash
docker compose up -d
```

## 4. Pull an Ollama model

```bash
docker exec -it glean-ollama ollama pull qwen2.5:7b
```

## 5. Test a feed

```bash
docker exec -it glean glean test-feed ai-news-daily
```

This runs a dry-run — fetches sources, runs the pipeline, and prints what would be sent without actually posting to Telegram.

## CLI reference

```
glean run                       # daemon; container entrypoint
glean test-feed <name>          # dry-run; prints would-be message
glean test-feed <name> --send   # like above but actually sends
glean send-now <name>           # immediate run, send for real
glean list-feeds                # feeds + last-run state
glean validate-config           # exit 0/1; prints errors
glean version
```

All commands accept `--config <path>` and `--db <path>`.
