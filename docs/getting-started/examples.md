---
title: "Examples — glean Getting Started"
description: Five self-contained examples that spin up a working glean stack in one command.
---

# Examples

Each example bundles its own `docker-compose.yml`, `feeds.yaml`, and setup script. Pick one, run `./setup.sh` (or `./setup.ps1` on Windows), and you have a working glean stack in minutes.

## Quick chooser

### 01 — `web-search-local-llm`

This example is the fastest path to a fully self-hosted glean stack: SearXNG finds fresh links, Ollama summarizes them with `qwen2.5:7b`, and glean writes the digest to a markdown file while also keeping it in the dashboard. Expect your first digest in about 10 minutes, mostly spent pulling the local model.

```bash
cd examples/01-web-search-local-llm && ./setup.sh
```

**Best for:** Self-hosted search.

### 02 — `ai-news-discord`

This setup turns three RSS feeds into a daily AI-news newsletter for a Discord channel, with Ollama handling the ranking and summaries locally and the dashboard preserving recent runs for review. Time to first digest is about 10 minutes once the model is available.

```bash
cd examples/02-ai-news-discord && ./setup.sh
```

**Best for:** Daily AI newsletter.

### 03 — `github-releases-slack`

This example skips LLMs entirely and watches five GitHub `releases.atom` feeds, deduplicating and forwarding only new releases into Slack plus the built-in dashboard. Because there is no model pull, you can usually get the first digest in about 2 minutes.

```bash
cd examples/03-github-releases-slack && ./setup.sh
```

**Best for:** DevOps teams.

### 04 — `arxiv-skill-ntfy`

This stack pulls arXiv RSS, runs a structured skill over each paper, sends phone-friendly push notifications through ntfy, and archives structured output to JSONL alongside the dashboard history. It uses Ollama locally, so plan on roughly 10 minutes to the first digest.

```bash
cd examples/04-arxiv-skill-ntfy && ./setup.sh
```

**Best for:** Researchers.

### 05 — `reddit-cloud-telegram`

This example watches machine-learning-focused Reddit communities, uses a cloud LLM for ranking and summaries, and delivers the digest to Telegram while keeping the dashboard available for inspection. With no local model pull, the first digest usually arrives in about 3 minutes.

```bash
cd examples/05-reddit-cloud-telegram && ./setup.sh
```

**Best for:** Cloud-LLM users.

## Conventions

Every example follows the same shape so they can coexist on one host: container names prefixed `glean-exNN-*`, dedicated bridge networks `glean-exNN`, distinct host ports for the API (`9091`-`9095`), and relative `./data/` volumes that are gitignored per example.

See [`examples/README.md`](https://github.com/jaypetez/glean/tree/main/examples) for the full add-an-example guide.

## What runs where

| Example | Glean | Ollama? | External secrets required |
|---------|-------|---------|----------------------------|
| 01 | `glean-ex01-glean` :9091 | yes (qwen2.5:7b) | none (SearXNG self-hosted) |
| 02 | `glean-ex02-glean` :9092 | yes (qwen2.5:7b) | `DISCORD_WEBHOOK_URL` |
| 03 | `glean-ex03-glean` :9093 | **no** | `SLACK_WEBHOOK_URL` |
| 04 | `glean-ex04-glean` :9094 | yes (qwen2.5:7b) | `NTFY_TOPIC` (no account needed) |
| 05 | `glean-ex05-glean` :9095 | **no** | `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) + Telegram bot |

## See also

- [Quickstart](quickstart.md)
- [Concepts overview](../concepts/index.md)
- [How-to: Sinks](../how-to/sinks/index.md)
