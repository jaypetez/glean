# 01 - Web search -> local LLM -> file + dashboard sinks

A fully self-hosted glean stack that:

- Searches the open web every hour via **SearXNG** (no API keys, no telemetry).
- Summarizes each result with **Ollama** running `qwen2.5:7b` (~5 GB RAM at Q4_K_M, fits comfortably under 16 GB).
- Writes the rendered digest to `./data/digests/web-search.md` and stores recent digests in the built-in dashboard UI (no Telegram / Discord / Slack required).

Three containers: `glean-ex01-glean`, `glean-ex01-ollama`, `glean-ex01-searxng`. All on a private bridge network.

## Requirements

- Docker 24+ with `docker compose` v2
- `openssl` (for generating SearXNG's secret)
- `curl` (for verifying healthz)
- ~10 GB free disk for the Ollama model + container images
- >=16 GB RAM (8 GB is fine for the model; the rest is headroom)

## GPU acceleration

`setup.sh` / `setup.ps1` auto-detect the best Ollama mode for your machine:

| What you have | Detected as | What happens |
|---------------|-------------|--------------|
| Native Ollama already running on your host (`ollama serve` listening on `11434`) | `external` | Skips the ollama container, points glean at `host.docker.internal:11434`. **Best path for macOS** (Docker on Mac cannot pass the GPU through). |
| NVIDIA GPU + [`nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) | `nvidia` | Container gets GPU passthrough via `deploy.resources.reservations.devices`. |
| AMD GPU + ROCm | `rocm` | Switches to `ollama/ollama:rocm` image + mounts `/dev/kfd` + `/dev/dri`. |
| Anything else | `none` | CPU only - fine for `qwen2.5:7b` on modern hardware. |

**Override detection** by setting `GLEAN_OLLAMA_GPU=none|nvidia|rocm|external` in `.env`.

**macOS**: macOS Docker Desktop runs in a Linux VM with no Metal access. Install Ollama natively (`brew install ollama && ollama serve`), pull the model (`ollama pull qwen2.5:7b`), then run `./setup.sh` - it auto-detects `external` mode.

**NVIDIA (Linux + Windows WSL2)**: install `nvidia-container-toolkit`, then `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker` (Linux) or restart Docker Desktop (Windows). Sanity-check: `docker run --rm --gpus=all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi`.

**AMD ROCm**: Linux only. See [Ollama AMD GPU docs](https://github.com/ollama/ollama/blob/main/docs/gpu.md#amd-radeon).

## One-shot setup

```bash
./setup.sh        # Linux / macOS / WSL
```

```powershell
./setup.ps1       # Windows PowerShell
```

The script generates `.env`, auto-detects the best Ollama mode for your machine, brings up the stack, pulls `qwen2.5:7b` when needed, runs a dry-run of the feed, and prints next steps.

It is idempotent - re-running just verifies the stack is healthy.

## What the feed does

`feeds.yaml` defines one feed:

| Setting | Value |
|---------|-------|
| Schedule | `every 1h` |
| Sources | SearXNG search for "open source AI news" (10 results / tick) |
| Pipeline | `dedup -> rank (min 0.5) -> summarize -> digest` |
| LLM | `ollama:qwen2.5:7b` at `http://ollama:11434` |
| Sink | `file` -> `/data/digests/web-search.md` (markdown) + `dashboard` -> last 50 digests in the web UI |
| Bootstrap | `skip-and-mark` (first tick indexes silently; sends only from the second tick onward) |

Change the search query by editing the `query:` field under `sources:` in `feeds.yaml`, then restart: `docker compose -f docker-compose.yml restart glean`.

## Browsing digests in a browser

The example wires up two sinks by default:

- **`file`** writes the digest to `./data/digests/web-search.md` (good for `tail -f`, `cat`, or opening in an editor)
- **`dashboard`** persists the digest to glean's state DB so you can browse it in the built-in web UI

To open the UI:

1. Get the API key (auto-generated on first start):

   ```bash
   docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY | head -1
   ```

2. Open http://127.0.0.1:9091/ in your browser.

3. Paste the API key when prompted. The "Digests" tab shows the last 50 digests per feed, newest first. New digests appear automatically - no refresh needed.

See [`docs/how-to/sinks/dashboard.md`](../../docs/how-to/sinks/dashboard.md) for full sink reference.

## Sending a digest right now (skip the wait)

```bash
docker compose -f docker-compose.yml exec glean glean send-now web-search
```

This forces a one-off run, writes to `data/digests/web-search.md`, and stores the digest in the dashboard. The next scheduled tick still fires on the hour.

## Inspecting state

```bash
# Tail the running glean logs (JSON in container, text on host)
docker compose -f docker-compose.yml logs -f glean

# See which items glean has already seen (dedup table)
docker compose -f docker-compose.yml exec glean \
  sqlite3 /data/state.db 'SELECT canonical_url, sent_at FROM seen_items LIMIT 20;'

# Look at the digest output
cat data/digests/web-search.md
```

## Teardown

```bash
./teardown.sh
```

Removes containers, volumes, the `data/` directory, and the local `.env`. The example directory itself is preserved so you can re-run `setup.sh`.

## Going further

- Swap the LLM model: edit `defaults.llm.model` in `feeds.yaml` and pull the new model into Ollama. Tested models that fit comfortably in 16 GB:
  - `qwen2.5:7b` (default - fast)
  - `qwen2.5:14b` (slower but noticeably better summaries; ~9 GB)
  - `llama3.1:8b` (alternative; ~5 GB)
- Add a second sink (Telegram, Discord, ntfy): see `docs/how-to/sinks/`.
- Add a structured-extraction skill (e.g. extract CVE IDs from security advisories): see `docs/concepts/skills.md`.
- Run multiple search queries in one feed: duplicate the `- type: search` block under `sources:`.