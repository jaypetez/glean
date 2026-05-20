---
title: "Examples — glean Getting Started"
description: Six self-contained examples that spin up a working glean stack in one command.
---

# Examples

Each example bundles its own `docker-compose.yml`, `feeds.yaml`, and setup script. Pick one, run `./setup.sh` (or `./setup.ps1` on Windows), and you have a working glean stack in minutes.

## Quick chooser

### 01 — `web-search-local-llm`

This example is the fastest path to a fully self-hosted glean stack: SearXNG finds fresh links, Ollama suppresses near-duplicate hits with `nomic-embed-text`, summarizes them with `qwen2.5:7b`, and glean writes the digest to a markdown file while also keeping it in the dashboard. Expect your first digest in about 10 minutes, mostly spent pulling the local models.

```bash
cd examples/01-web-search-local-llm && ./setup.sh
```

**Best for:** Self-hosted search.

### 02 — `ai-news-discord`

This setup turns three RSS feeds into a daily AI-news newsletter for a Discord channel, with Ollama suppressing near-duplicate stories via `nomic-embed-text`, handling ranking and summaries locally with `qwen2.5:7b`, and the dashboard preserving recent runs for review. Time to first digest is about 10 minutes once the models are available.

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

This stack pulls arXiv RSS, suppresses near-duplicate papers with `nomic-embed-text`, runs a structured skill over each paper, sends phone-friendly push notifications through ntfy, and archives structured output to JSONL alongside the dashboard history. It uses Ollama locally, so plan on roughly 10 minutes to the first digest.

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

### 06 — `weekly-newsletter`

This example turns a weekly RSS digest into a styled HTML email, delivered locally through Mailpit for safe testing while the dashboard keeps a second copy for review. It uses Ollama for local ranking and summaries, so expect roughly 10 minutes to the first digest while models are pulled.

```bash
cd examples/06-weekly-newsletter && ./setup.sh
```

**Best for:** Email users.

## Conventions

Every example follows the same shape so they can coexist on one host: container names prefixed `glean-exNN-*`, dedicated bridge networks `glean-exNN`, distinct host ports for the API (`9091`-`9096`), and relative `./data/` volumes that are gitignored per example.

See [`examples/README.md`](https://github.com/jaypetez/glean/tree/main/examples) for the full add-an-example guide.

## What runs where

| Example | Glean | Ollama? | External secrets required | Highlights |
|---------|-------|---------|----------------------------|------------|
| 01 | `glean-ex01-glean` :9091 | yes (`qwen2.5:7b` + `nomic-embed-text`) | none (SearXNG self-hosted) | Self-hosted web search + semantic dedup |
| 02 | `glean-ex02-glean` :9092 | yes (`qwen2.5:7b` + `nomic-embed-text`) | `DISCORD_WEBHOOK_URL` | RSS newsletter + semantic dedup |
| 03 | `glean-ex03-glean` :9093 | **no** | `SLACK_WEBHOOK_URL` | No LLMs; exact dedup only |
| 04 | `glean-ex04-glean` :9094 | yes (`qwen2.5:7b` + `nomic-embed-text`) | `NTFY_TOPIC` (no account needed) | Research feed + semantic dedup + skills |
| 05 | `glean-ex05-glean` :9095 | **no** | `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) + Telegram bot | Cloud LLM + exact dedup |
| 06 | `glean-ex06-glean` :9096 | yes (`qwen2.5:7b`) | none (Mailpit local) | Weekly HTML email + dashboard |

## GPU acceleration for Ollama

Examples that include Ollama ([01](https://github.com/jaypetez/glean/blob/main/examples/01-web-search-local-llm/README.md), [02](https://github.com/jaypetez/glean/blob/main/examples/02-ai-news-discord/README.md), [04](https://github.com/jaypetez/glean/blob/main/examples/04-arxiv-skill-ntfy/README.md), and [06](https://github.com/jaypetez/glean/blob/main/examples/06-weekly-newsletter/README.md)) auto-detect your hardware and configure the stack accordingly. Run `./setup.sh` (or `./setup.ps1` on Windows) and the script tells you which mode it picked.

Those four examples also pre-pull `qwen2.5:7b`; examples [01](https://github.com/jaypetez/glean/blob/main/examples/01-web-search-local-llm/README.md), [02](https://github.com/jaypetez/glean/blob/main/examples/02-ai-news-discord/README.md), and [04](https://github.com/jaypetez/glean/blob/main/examples/04-arxiv-skill-ntfy/README.md) additionally pull `nomic-embed-text` because they showcase semantic dedup.

### Detection order

1. **External Ollama** — if `http://host.docker.internal:11434/api/tags` (or `http://127.0.0.1:11434/api/tags`) returns 200, the example skips its own Ollama container and points glean at your host's instance. **Best path for macOS**.
2. **NVIDIA** — `nvidia-smi` exits 0 and Docker is configured for NVIDIA GPU access, so setup adds `docker-compose.nvidia.yml` and mounts the NVIDIA driver into the container via `deploy.resources.reservations.devices`. Requires [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).
3. **AMD ROCm** — `rocm-smi` plus `/dev/kfd` present means setup adds `docker-compose.rocm.yml`, switches to the `ollama/ollama:rocm` image, and mounts `/dev/kfd` plus `/dev/dri`. Linux only.
4. **CPU fallback** — if none of the above is detected, setup uses only the base compose file. This still works well for `qwen2.5:7b` on modern hardware.

| Detected | When | Compose used |
|----------|------|--------------|
| `external` | Native Ollama on the host responds on port `11434` | `+ docker-compose.external-ollama.yml` |
| `nvidia` | `nvidia-smi` available + NVIDIA Container Toolkit installed | `+ docker-compose.nvidia.yml` |
| `rocm` | `rocm-smi` + `/dev/kfd` present (Linux only) | `+ docker-compose.rocm.yml` |
| `none` | None of the above | base compose only (CPU) |

### Overriding detection

Set `GLEAN_OLLAMA_GPU=none|nvidia|rocm|external` in the example's `.env` to force a mode. The setup scripts validate the value up front; if you force a mode whose runtime prerequisites are not actually available, Docker or Ollama startup fails and the example tells you what runtime still needs to be installed.

### Platform-specific setup

**macOS** — Docker on Mac runs in a Linux VM with no Metal access. Install Ollama natively, then setup auto-detects `external` mode:

```bash
brew install ollama
ollama serve &              # in another terminal or as a service
ollama pull qwen2.5:7b      # ranking + summaries
ollama pull nomic-embed-text # semantic dedup embeddings
cd examples/01-web-search-local-llm && ./setup.sh
```

**Linux / Windows with NVIDIA** — install the container toolkit, configure Docker, then setup auto-detects:

```bash
# Linux: install nvidia-container-toolkit per https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
# Windows WSL2: install the toolkit inside WSL, restart Docker Desktop
# Sanity check:
docker run --rm --gpus=all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

**Linux with AMD ROCm** — see [Ollama AMD GPU docs](https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon) for host setup details, then run the example normally.

See the example READMEs for the per-stack details and caveats: [01 — web-search-local-llm](https://github.com/jaypetez/glean/blob/main/examples/01-web-search-local-llm/README.md), [02 — ai-news-discord](https://github.com/jaypetez/glean/blob/main/examples/02-ai-news-discord/README.md), [04 — arxiv-skill-ntfy](https://github.com/jaypetez/glean/blob/main/examples/04-arxiv-skill-ntfy/README.md), and [06 — weekly-newsletter](https://github.com/jaypetez/glean/blob/main/examples/06-weekly-newsletter/README.md).

## See also

- [Quickstart](quickstart.md)
- [Concepts overview](../concepts/index.md)
- [How-to: Sinks](../how-to/sinks/index.md)
