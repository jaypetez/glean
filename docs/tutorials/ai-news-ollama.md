---
title: "Build an AI news digest with Ollama and Telegram — glean Tutorial"
description: "Create a working hourly AI news Telegram digest using Docker, local Ollama, RSS sources, and glean."
---

# Build an AI news digest with Ollama and Telegram

In this tutorial, you'll build a feed that watches AI news sources, summarizes new items with a local Ollama model, and posts an hourly digest to a Telegram channel.

## Prerequisites

- Docker installed with Compose v2 (`docker compose version` works)
- About 10 GB free disk for Ollama models
- A Telegram account
- A new empty directory for the tutorial files

## Step 1 — Create a Telegram bot

Open Telegram and start a chat with [@BotFather](https://t.me/BotFather). Send these messages:

```text
/newbot
AI News Gleaner
ai_news_gleaner_bot
```

BotFather replies with a token that looks like this:

```text
Use this token to access the HTTP API:
1234567890:AAExampleTokenExampleTokenExampleToken
```

Copy the token. It becomes `TELEGRAM_BOT_TOKEN` in the next step.

!!! why "Why a bot token?"
    Telegram only lets software send messages through a bot identity. glean never logs in as your user account; it calls the Telegram Bot API with this token.

## Step 2 — Add the bot to a group and get the chat ID

Create a Telegram group or use an existing one. Add your new bot to the group, then send a message such as:

```text
hello glean
```

Ask Telegram for recent bot updates. Replace the token with your real token:

```bash
curl "https://api.telegram.org/bot1234567890:AAExampleTokenExampleTokenExampleToken/getUpdates"
```

Expected output includes a `chat` object:

```json
{
  "ok": true,
  "result": [
    {
      "message": {
        "chat": {
          "id": -1001234567890,
          "title": "AI News",
          "type": "supergroup"
        },
        "text": "hello glean"
      }
    }
  ]
}
```

Copy the `chat.id`. Group and supergroup IDs are usually negative. It becomes `TELEGRAM_CHAT_AI`.

## Step 3 — Configure glean

Create the working files:

```bash
mkdir -p data
cat > .env <<'EOF'
TELEGRAM_BOT_TOKEN=1234567890:AAExampleTokenExampleTokenExampleToken
TELEGRAM_CHAT_AI=-1001234567890
TELEGRAM_OPS_CHAT_ID=-1001234567890
EOF
```

Create `feeds.yaml`:

```bash
cat > feeds.yaml <<'EOF'
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
  failure:
    alert_after: 3
    ops_chat_id: ${TELEGRAM_OPS_CHAT_ID}

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
      - type: rss
        url: http://export.arxiv.org/rss/cs.AI
    pipeline:
      - dedup
      - rank:
          prompt: |
            Score 0-1 for relevance to engineers following practical AI.
            Boost releases, research, tools, evals, and deployment lessons.
            Penalize celebrity news, vague funding news, and duplicate commentary.
          min_relevance: 0.45
      - summarize:
          prompt: |
            Write one sentence for a Telegram digest. Lead with the concrete news.
            Keep it under 25 words. No marketing language.
      - digest:
          intro: "🧠 <b>AI news this hour</b>"
EOF
```

Create `compose.yaml`:

```bash
cat > compose.yaml <<'EOF'
services:
  glean:
    image: ghcr.io/jaypetez/glean:1.3.0
    container_name: glean
    restart: unless-stopped
    depends_on:
      - ollama
    env_file:
      - .env
    environment:
      TZ: UTC
    volumes:
      - ./data:/data
      - ./feeds.yaml:/etc/glean/feeds.yaml:ro
    ports:
      - "127.0.0.1:9090:9090"
    networks:
      - glean

  ollama:
    image: ollama/ollama:latest
    container_name: glean-ollama
    restart: unless-stopped
    volumes:
      - ollama-models:/root/.ollama
    networks:
      - glean

volumes:
  ollama-models:

networks:
  glean:
    driver: bridge
EOF
```

!!! why "Why `bootstrap: send-last-N`?"
    The production default is `skip-and-mark`, which silently indexes existing items on the first real run and sends only future items. That is safer for long-lived feeds, but it can look like nothing works during a tutorial. This tutorial asks for a small first digest so you get visible confirmation quickly.

## Step 4 — Start glean and pull a model

Start Ollama first, wait until it answers, then pull the model before starting glean:

```bash
docker compose up -d ollama
until docker compose exec ollama ollama list >/dev/null 2>&1; do sleep 1; done
docker compose exec ollama ollama pull qwen2.5:7b
docker compose up -d glean
```

Expected output is similar to:

```text
[+] Running 2/2
 ✔ Network ai-news-ollama_glean      Created
 ✔ Container glean-ollama            Started
pulling manifest
pulling ... 100%
success
[+] Running 2/2
 ✔ Container glean-ollama            Running
 ✔ Container glean                   Started
```

Check that the API is alive:

```bash
curl http://127.0.0.1:9090/healthz
```

Expected output starts with `"status":"ok"` and includes the database and scheduler checks:

```json
{"status":"ok","db":"ok","scheduler":"running","version":"1.3.0","uptime_s":42}
```

## Step 5 — Watch the first digest arrive

Run a dry-run first. It fetches sources and renders the digest without posting to Telegram:

```bash
docker compose exec glean glean test-feed ai-news-daily
```

Expected output:

```text
---
feed=ai-news-daily fetched=30 after_dedup=30 dropped=18 overflow=0 sent=0 duration_ms=8421
---  WOULD SEND  ---

[message 1]
🧠 <b>AI news this hour</b>

• <a href="https://example.com/ai-tool">Example AI tool release</a>
  Ships a practical model-serving update for local inference.
```

Now wait for the first scheduled tick or send immediately:

```bash
docker compose exec glean glean send-now ai-news-daily
```

Expected output ends with `sent=` greater than zero:

```text
---
feed=ai-news-daily fetched=30 after_dedup=30 dropped=18 overflow=0 sent=5 duration_ms=9012
```

You should see a message in the Telegram group headed:

```text
🧠 AI news this hour
```

!!! why "Why dry-run first?"
    `test-feed` is safe: it does not send Telegram messages and does not mark items as seen. It is the fastest way to separate configuration problems from delivery problems.

## Step 6 — Customize the prompt

Edit the `rank` and `summarize` prompts in `feeds.yaml`. For example, make the digest favor open-source releases:

```yaml
      - rank:
          prompt: |
            Score 0-1 for relevance to engineers who build with open-source AI tools.
            Boost local inference, evals, agents, RAG, model releases, and reproducible demos.
            Penalize funding announcements and unsourced speculation.
          min_relevance: 0.5
      - summarize:
          prompt: |
            Write one crisp sentence. Mention the project, release, or paper name when available.
            Keep it under 25 words.
```

Restart glean so the container re-reads the mounted config:

```bash
docker compose restart glean
```

Expected output:

```text
[+] Restarting 1/1
 ✔ Container glean  Started
```

Dry-run again to compare the digest:

```bash
docker compose exec glean glean test-feed ai-news-daily
```

## What's next

- Add another source: see [Authoring Sources](../plugins/source.md).
- Use a paid LLM for higher-quality digests: see the [LLM how-to guides](../how-to/llm/index.md).
- Understand the bootstrap behavior: see [Dedup and Bootstrap](../concepts/dedup-bootstrap.md).
