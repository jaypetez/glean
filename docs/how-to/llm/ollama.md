---
title: "How to set up Ollama — glean"
description: "Use the bundled or external Ollama server as glean's local LLM provider."
---

# How to set up Ollama

**Goal:** Run ranking, summaries, and digest headers with a local Ollama model.

**You need:**

- Docker Compose, or an existing Ollama server.
- Enough RAM for the model you choose.
- A model pulled into Ollama before the feed runs.

## Steps

1. Start the bundled compose stack:

   ```bash
   docker compose up -d
   ```

2. Pull a model in the bundled Ollama container:

   ```bash
   docker exec glean-ollama ollama pull qwen2.5:7b
   ```

   If your local compose file names the container `ollama-glean`, use that name in the same command.

3. Choose a model:

   - `qwen2.5:0.5b` for smoke tests and tiny machines.
   - `qwen2.5:7b` for the default production setup.
   - `llama3:8b` as a strong alternative if you already use Llama models.

4. Configure the default LLM:

   ```yaml
   defaults:
     llm:
       provider: ollama
       model: qwen2.5:7b
   ```

5. If Ollama is not the bundled compose service, set `base_url`:

   ```yaml
   defaults:
     llm:
       provider: ollama
       model: qwen2.5:7b
       base_url: http://host.docker.internal:11434
   ```

6. Use CPU for small feeds or testing. Use a GPU-backed Ollama host when larger models or many feed items make runs too slow.

## Verify

Run:

```bash
docker exec glean-ollama ollama list
uv run glean validate-config -c feeds.yaml
```

Expected output includes:

```text
qwen2.5:7b
OK — 1 feed(s)
```

## Next steps

- [Use per-source LLM dispatch for cheap and premium sources](per-source.md)
- [LLM provider reference](../../config/feeds.md#llm-providers)
