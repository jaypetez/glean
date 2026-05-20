# 04 — arXiv papers → skill extraction → ntfy + JSONL

A self-hosted glean stack that watches **arXiv cs.AI + cs.LG**, suppresses near-duplicate papers with semantic dedup, ranks for practical ML-engineering relevance, extracts structured paper metadata with a reusable skill, pushes the digest to **ntfy.sh**, and archives each paper as **JSONL** while also keeping recent digests in the built-in dashboard.

Two containers: `glean-ex04-glean` and `glean-ex04-ollama`. Both run on the private `glean-ex04` bridge network.

## Requirements

- Docker 24+ with `docker compose` v2
- `curl` (used by the setup script health checks)
- ~10 GB free disk for the Ollama models + container images (`qwen2.5:7b` + `nomic-embed-text` still fit in the same budget)
- Enough RAM for `qwen2.5:7b` (≈8–16 GB is comfortable)

## GPU acceleration

The setup scripts auto-detect the best Ollama mode in this order: `external`, `nvidia`, `rocm`, then `none` (CPU-only). Set `GLEAN_OLLAMA_GPU=none|nvidia|rocm|external` in `.env` to force a specific mode.

| Mode | Auto-detected when | Compose override | Notes |
|------|---------------------|------------------|-------|
| `external` | `http://host.docker.internal:11434` or `http://127.0.0.1:11434` already serves Ollama | `docker-compose.external-ollama.yml` | Reuses the host Ollama instance and skips the model pull. |
| `nvidia` | `nvidia-smi` succeeds on the host | `docker-compose.nvidia.yml` | Requires NVIDIA drivers plus `nvidia-container-toolkit`. |
| `rocm` | `rocm-smi` exists and `/dev/kfd` is present | `docker-compose.rocm.yml` | Requires a Linux host with ROCm devices exposed to Docker. |
| `none` | No external Ollama or GPU runtime is detected | none | Uses the default CPU-only `ollama/ollama:latest` container. |

The setup script prints the chosen GPU mode, verifies the GPU inside the Ollama container for NVIDIA/ROCm, and restores `feeds.yaml` on teardown if external mode patched it.

## One-shot setup

```bash
./setup.sh
```

```powershell
./setup.ps1
```

The script copies `.env.example` to `.env` if needed, verifies you chose a private ntfy topic, auto-detects the Ollama runtime, starts Ollama, pulls `qwen2.5:7b` plus `nomic-embed-text` unless you're using an external Ollama, starts glean on port **9094**, and dry-runs the `arxiv-papers` feed.

## Subscribe on your phone

1. Install [ntfy](https://ntfy.sh) from the App Store / Play Store, or use the ntfy web UI.
2. Open your topic name from `.env` (for example `https://ntfy.sh/<your-topic>`).
3. That's it — no account and no API key required.

## What the feed does

| Sink | Format | Purpose |
|------|--------|---------|
| `ntfy` | Plain push notification | Delivers the ranked daily paper digest to your phone |
| `file` | JSONL | Appends one JSON object per paper to `/data/digests/arxiv-papers.jsonl` |
| `dashboard` | Stored rendered digest | Keeps the last 50 digests in the built-in web UI |

The feed runs daily at `09:00`, reads arXiv RSS for `cs.AI` and `cs.LG`, suppresses near-duplicate papers with `semantic_dedup` (`nomic-embed-text`, `min_similarity: 0.88`, `window: 7d`), ranks items for weekend-project practicality, applies the `paper-digest` skill, and renders a short intro: `arXiv: top papers today`.

## What semantic dedup suppresses

After URL dedup, `semantic_dedup` embeds each paper title and abstract with `nomic-embed-text` and suppresses papers that closely match something this feed already sent in the last 7 days.
See [Semantic dedup](../../docs/concepts/semantic-dedup.md) for threshold tuning, window sizing, and model choices.

## Inspecting the structured JSONL

```bash
tail -f data/digests/arxiv-papers.jsonl | jq '.structured'
```

## Viewing digests in the browser

1. Get the API key from the logs:

   ```bash
   docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY | head -1
   ```

2. Open http://127.0.0.1:9094/ in your browser.
3. Paste the API key when prompted, then open the **Digests** tab.

## Customizing arXiv categories

Edit the RSS URLs in `feeds.yaml:47-51` to swap in other categories from the [arXiv taxonomy](https://arxiv.org/category_taxonomy). For example, replace `cs.LG` with `cs.CL` or add more `rss` sources under the same feed.

## Editing the skill

The reusable extraction template lives in the `skills:` block at `feeds.yaml:14-30`. Tweak the prompt, schema, or system prompt there, then see [skills concepts](../../docs/concepts/skills.md) for how `apply_skill` populates structured fields and summary text.

## Teardown

```bash
./teardown.sh
```

```powershell
./teardown.ps1
```

This stops the stack, removes containers and volumes, deletes the local `.env` plus `data/` directory, and restores `feeds.yaml` if external Ollama mode patched it.

## Going further

- Point `ntfy` at a self-hosted server by uncommenting `base_url` in `feeds.yaml`.
- Add more arXiv categories or feeds to compare different subfields.
- Change the model in `defaults.llm.model` if you want a larger or faster extractor.
- Pipe the JSONL archive into notebooks, scripts, or downstream ETL jobs.
