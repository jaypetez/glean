---
title: "Quickstart — glean Getting Started"
description: Get a first glean feed running with Docker, Ollama, and Telegram.
---

# Quickstart

This is the shortest path to a working AI news digest with local Ollama and Telegram.

## 1. Create `.env`

Create a Telegram bot with [@BotFather](https://t.me/BotFather), add it to a group, send one message, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` to find the group `chat.id`.

Minimum `.env`:

```bash
TELEGRAM_BOT_TOKEN=1234567890:AAExampleTokenExampleTokenExampleToken
TELEGRAM_CHAT_AI=-1001234567890
TELEGRAM_OPS_CHAT_ID=-1001234567890
```

## 2. Create `feeds.yaml`

```yaml
defaults:
  telegram:
    bot_token: ${TELEGRAM_BOT_TOKEN}
  llm:
    provider: ollama
    model: qwen2.5:7b
    base_url: http://ollama:11434
  render:
    style: html
    link_preview: false
    max_items: 5

feeds:
  - name: ai-news-daily
    schedule: "every 1h"
    bootstrap: send-last-N
    bootstrap_count: 5
    chat_id: ${TELEGRAM_CHAT_AI}
    sources:
      - type: rss
        url: https://simonwillison.net/atom/everything/
      - type: rss
        url: https://hnrss.org/newest?q=ai
    pipeline:
      - dedup
      - rank:
          prompt: "Score 0-1 for practical AI engineering relevance."
          min_relevance: 0.45
      - summarize:
          prompt: "One sentence under 25 words. No marketing fluff."
      - digest:
          intro: "🧠 <b>AI news this hour</b>"
```

## 3. Start with Docker Compose

```bash
mkdir -p data
cat > compose.yaml <<'EOF'
services:
  glean:
    image: ghcr.io/jaypetez/glean:1.3.0
    depends_on: [ollama]
    env_file: [.env]
    volumes:
      - ./data:/data
      - ./feeds.yaml:/etc/glean/feeds.yaml:ro
    ports:
      - "127.0.0.1:9090:9090"
    networks: [glean]

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama-models:/root/.ollama
    networks: [glean]

volumes:
  ollama-models:

networks:
  glean:
    driver: bridge
EOF

docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:7b
docker compose up -d glean
```

## 4. Dry-run the feed

```bash
docker compose exec glean glean test-feed ai-news-daily
```

Sample output:

```text
---
feed=ai-news-daily fetched=18 after_dedup=18 dropped=9 overflow=0 sent=0 duration_ms=6420
---  WOULD SEND  ---

[message 1]
🧠 <b>AI news this hour</b>

• <a href="https://example.com/ai-release">Example AI release</a>
  Adds a practical local-inference feature for engineers.
```

Send once now:

```bash
docker compose exec glean glean send-now ai-news-daily
```

!!! tip "Not using Telegram?"
    glean can send the same digest to other sinks. See the sink how-tos for [Discord](../how-to/sinks/index.md), [Slack](../how-to/sinks/index.md), [ntfy](../how-to/sinks/index.md), [webhooks](../how-to/sinks/index.md), and [files](../how-to/sinks/index.md).

## Quickstart without LLM

This path uses only `dedup → digest` and writes to a file sink. No LLM API key, model, Telegram bot, or `.env` file is needed.

```yaml
feeds:
  - name: rss-to-file
    schedule: "every 1h"
    bootstrap: send-all
    sinks:
      - type: file
        path: /data/rss-digest.md
        format: markdown
    sources:
      - type: rss
        url: https://simonwillison.net/atom/everything/
    pipeline:
      - dedup
      - digest:
          intro: "RSS digest"
```

Dry-run it:

```bash
docker run --rm \
  -v "$(pwd)/feeds.yaml:/etc/glean/feeds.yaml:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/jaypetez/glean:1.3.0 \
  test-feed rss-to-file
```

## What's next

- Build the full first feed in [Build an AI news digest with Ollama and Telegram](../tutorials/ai-news-ollama.md).
- Understand the model in [Concepts](../concepts/index.md).
- Look up every field in the [feeds.yaml reference](../config/feeds.md).
