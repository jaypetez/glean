# 02 — AI news → Ollama → Discord + dashboard

A self-hosted daily AI-news example for glean. It pulls from three RSS feeds, uses semantic dedup to suppress overlapping stories, summarizes them with a local Ollama model, posts to Discord via webhook, and keeps recent digests in the built-in dashboard.

## Requirements

- Docker 24+ with `docker compose` v2
- `curl` (used by `setup.sh` to verify `healthz`)
- ~10 GB free disk for the Ollama models + container images (`qwen2.5:7b` + `nomic-embed-text` still fit in the same budget)
- ~8 GB RAM minimum for `qwen2.5:7b` (more headroom helps on CPU-only hosts)

## GPU acceleration

The setup scripts auto-detect the best Ollama mode in this order: `external` → `nvidia` → `rocm` → `none`.

| Mode | What happens | Auto-selected when | Requirements |
|------|--------------|--------------------|--------------|
| `external` | `glean` connects to Ollama already running on the host at `http://host.docker.internal:11434` | A host Ollama responds on port `11434` | Host Ollama running, with `qwen2.5:7b` and `nomic-embed-text` already pulled |
| `nvidia` | Adds NVIDIA GPU passthrough to the bundled Ollama container | `nvidia-smi` works on the host | NVIDIA GPU + drivers + `nvidia-container-toolkit`, then restart Docker |
| `rocm` | Switches the bundled Ollama container to `ollama/ollama:rocm` and passes through `/dev/kfd` + `/dev/dri` | `rocm-smi` exists and `/dev/kfd` is present | ROCm-capable AMD GPU on Linux |
| `none` | Uses the default CPU-only Ollama container | No external Ollama or compatible GPU is detected | No extra setup |

To force a mode, set `GLEAN_OLLAMA_GPU=none|nvidia|rocm|external` in `.env` before running setup.

In `external` mode, the setup script temporarily rewrites `feeds.yaml` to point at `host.docker.internal` and restores the original file during teardown. In `nvidia` and `rocm` modes, the script also checks whether the Ollama container can actually see the GPU and prints guidance if Docker still needs host GPU runtime setup.

## One-shot setup

```bash
./setup.sh        # Linux / macOS / WSL
```

```powershell
./setup.ps1       # Windows PowerShell
```

The setup script copies `.env.example` to `.env`, checks your Discord webhook, auto-detects the Ollama mode, starts Ollama, pulls `qwen2.5:7b` plus `nomic-embed-text` when needed, starts glean, runs a dry-run, and prints next steps.

## Getting a Discord webhook URL

1. In Discord, open **Server Settings → Integrations → Webhooks**.
2. Click **New Webhook**, choose the target channel, then click **Copy Webhook URL**.
3. Paste that URL into `.env` as `DISCORD_WEBHOOK_URL=...`, then run the setup script.

## What the feed does

| Setting | Value |
|---------|-------|
| Schedule | `daily 08:00` |
| Sources | Simon Willison Atom, OpenAI blog RSS, HN RSS for `AI` |
| Pipeline | `dedup → semantic_dedup → rank (min 0.5) → summarize → digest` |
| Semantic dedup | `ollama:nomic-embed-text`, `min_similarity: 0.82`, `window: 7d` |
| LLM | `ollama:qwen2.5:7b` at `http://ollama:11434` |
| Sinks | `discord` webhook + `dashboard` (last 50 digests) |
| Bootstrap | `skip-and-mark` |

## What semantic dedup suppresses

After URL dedup, `semantic_dedup` embeds each story with `nomic-embed-text` and suppresses near-duplicates that closely match something this feed already sent in the last 7 days.
See [Semantic dedup](../../docs/concepts/semantic-dedup.md) for threshold tuning, window sizing, and model choices.

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
