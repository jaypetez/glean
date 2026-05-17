# 02 — AI news → Ollama → Discord + dashboard

A self-hosted daily AI-news example for glean. It pulls from three RSS feeds, deduplicates overlapping stories, summarizes them with a local Ollama model, posts to Discord via webhook, and keeps recent digests in the built-in dashboard.

## Requirements

- Docker 24+ with `docker compose` v2
- `curl` (used by `setup.sh` to verify `healthz`)
- ~10 GB free disk for the Ollama model + container images
- ~8 GB RAM minimum for `qwen2.5:7b` (more headroom helps on CPU-only hosts)

GPU acceleration is optional — this example works on CPU.

## One-shot setup

```bash
./setup.sh        # Linux / macOS / WSL
```

```powershell
./setup.ps1       # Windows PowerShell
```

The setup script copies `.env.example` to `.env`, checks your Discord webhook, starts Ollama, pulls `qwen2.5:7b`, starts glean, runs a dry-run, and prints next steps.

## Getting a Discord webhook URL

1. In Discord, open **Server Settings → Integrations → Webhooks**.
2. Click **New Webhook**, choose the target channel, then click **Copy Webhook URL**.
3. Paste that URL into `.env` as `DISCORD_WEBHOOK_URL=...`, then run the setup script.

## What the feed does

| Setting | Value |
|---------|-------|
| Schedule | `daily 08:00` |
| Sources | Simon Willison Atom, OpenAI blog RSS, HN RSS for `AI` |
| Pipeline | `dedup → rank (min 0.5) → summarize → digest` |
| LLM | `ollama:qwen2.5:7b` at `http://ollama:11434` |
| Sinks | `discord` webhook + `dashboard` (last 50 digests) |
| Bootstrap | `skip-and-mark` |

## Viewing digests in the browser

1. Open http://127.0.0.1:9092/ in your browser.
2. Grab the API key from logs:

   ```bash
   docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY
   # PowerShell: docker compose -f docker-compose.yml logs glean | Select-String GLEAN_INITIAL_API_KEY
   ```

3. Paste the key into the UI, then click the **Digests** tab to browse the dashboard sink output.

## Customizing

- Change the schedule by editing `schedule:` in `feeds.yaml`.
- Add or remove RSS sources under `sources:`.
- Swap the local model by editing `defaults.llm.model`, then pull that model into Ollama.

After changing `feeds.yaml`, restart glean:

```bash
docker compose -f docker-compose.yml restart glean
```

## Teardown

```bash
./teardown.sh
```

```powershell
./teardown.ps1
```

This removes the example containers, volumes, local `data/`, and `.env`.

## Going further

- [Skills concepts](../../docs/concepts/skills.md)
- [Discord sink how-to](../../docs/how-to/sinks/discord.md)
