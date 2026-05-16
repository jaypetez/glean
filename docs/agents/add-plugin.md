---
title: Add a New Plugin — Agent Runbook
description: Scaffold and ship a new Source/Sink/LLM Provider/Search Backend plugin.
---

# Add a new plugin

## Step 1 — Scaffold

If your checkout includes the PR2 scaffold helper, run:

```bash
make new-plugin LAYER=source NAME=my-source
```

If it does not, use the 30-second scaffold in `../plugins/index.md` and create the same files manually.

This should create a source module and matching test under `src/glean/sources/` and `tests/` (for example `my_source.py` and `test_source_my_source.py`), plus a registry import and a `feeds.example.yaml` snippet.

## Step 2 — Implement

Edit the TODO blocks in `src/glean/sources/my_source.py`. The protocol is documented in `../plugins/source.md`.

## Step 2.5 — Network safety

If your plugin makes outbound HTTP requests, call `glean.security.ssrf.validate_url()` before sending them. See [Common Pitfalls](pitfalls.md) and `docs/operations/security.md`.

## Step 3 — Test

```bash
make test
uv run pytest tests/test_source_my_source.py -v
```

## Step 4 — Validate end-to-end

Add an entry to `tests/e2e/feeds.e2e.yaml` referencing your plugin, but only if a mock service already exists or can be added safely. Then run `make e2e`.

## Step 5 — Document

Add a row to the relevant README plugin table and, if the plugin is non-trivial, a section to `docs/plugins/<layer>.md`.

## Step 6 — PR

Conventional commit: `feat(plugins): add <name> source` (or `sink` / `llm` / `search`).
