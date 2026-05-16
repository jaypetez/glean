---
title: Glossary — glean Reference
description: Definitions for glean-specific terms, runtime concepts, and agent-facing jargon.
---

# Glossary

These are the project-specific terms that show up across the codebase, docs, logs, and agent runbooks.

## `alert_active`

Boolean flag stored on the `feed_runs` row for a feed. It flips to `1` when failures reach `failure.alert_after`, and it flips back to `0` on the next successful run that posts a recovery signal.

## `apply_skill`

Pipeline stage that runs a named skill against each item. It produces structured output on `Item.structured` and may also populate summary-like fields for existing renderers.

## Bootstrap

The first-run behavior for a feed. By default, glean uses `skip-and-mark`, which silently baselines current items instead of sending the backlog immediately.

## Bootstrap modes

The supported first-run behaviors: `skip-and-mark` (default), `send-last-N`, and `send-all`. They control what happens before a feed is considered bootstrapped.

## Canonical URL

The stable per-item URL stored on `Item.canonical_url`. It is the preferred dedup key and should identify the same piece of content across runs.

## CODEOWNERS

The repository file at `.github/CODEOWNERS` that assigns review ownership to paths. Protected branches use it to require human review on sensitive areas such as security code, migrations, or schema changes.

## Consecutive failures

The failure counter stored in `feed_runs.consecutive_failures`. It increments only when a tick fails after retry logic is exhausted, and resets to zero on success.

## Dedup

The process that drops items already seen for the same feed. glean hashes `canonical_url`, or `title + body[:512]` if the URL is empty, and stores that identity in `seen_items`.

## Defaults

The top-level shared configuration block in `feeds.yaml`. Feed-level settings inherit from defaults unless a feed overrides them.

## Dry-run

A run that executes the pipeline without sending through sinks or writing persistent state. `glean test-feed` is a dry-run unless `--send` is supplied.

## `effective_*()` methods

Helper methods on `FeedConfig` that merge per-feed overrides with Defaults. Always call these methods instead of reading raw fields like `feed.llm` directly.

## ETag cache

The `etag_cache` SQLite table and the surrounding helper methods in `StateStore`. Sources use it to send conditional HTTP requests and avoid re-downloading unchanged content.

## Feed

A unit of work that bundles sources, a pipeline, sinks, and a schedule. One APScheduler tick executes one feed through `Runner.run_feed`.

## `feed_runs`

SQLite table that stores per-feed runtime state such as `bootstrapped`, `consecutive_failures`, `alert_active`, `last_success_at`, and `last_error`.

## Import builtins (`_import_builtins()`)

The registry helper function that wires built-in plugins by importing their modules for decorator side effects. Adding a new built-in plugin requires editing the matching registry's `_import_builtins()` function.

## Item

The frozen, slotted dataclass in `src/glean/sources/base.py` that represents one fetched piece of content. Stages never mutate an Item in place; they create a new one with `dataclasses.replace()`.

## LLM precedence

The dispatch order for choosing an LLM configuration: skill override first, then source override, then feed override, then defaults. This lets one feed mix local and paid models without duplicating prompts.

## LLM Provider

A plugin that implements LLM-facing behaviors such as `rank`, `summarize`, `digest`, and `extract`. Built-in providers include Ollama, OpenAI, and Anthropic.

## MCP server

A Model Context Protocol bridge some agent environments use to expose repo-specific developer tools. In agent-enabled setups it may offer helpers for test execution, linting, log access, or read-only database inspection.

## MCP tool

One function exposed through an MCP server. Examples include read-only database queries, lint wrappers, or test runners; the exact tool list depends on the agent environment.

## ops chat

The Telegram destination used for operational alerts. It is configured through `ops_chat_id` on Defaults or on an individual feed.

## Output schema

The structured field definition attached to a skill. glean converts it to strict JSON Schema before calling a provider's `extract()` implementation.

## Pipeline

The ordered list of stages a feed applies to fetched items during a tick. Common stages are `dedup`, `rank`, `summarize`, `apply_skill`, and `digest`.

## Render mode

The Telegram formatting style for outgoing digests. Built-in modes are `html` (default), `markdown_v2`, and `plain`.

## Search Backend

A plugin that implements `search(query, *, http, limit)`. Search backends power the Search source; built-ins include SearXNG and multiple cloud providers.

## `seen_items`

SQLite table that stores dedup identities per feed. It records when an item was seen and whether it was treated as sent.

## Sink

A plugin that delivers rendered output somewhere. Built-in sinks include Telegram, Discord, Slack, ntfy, webhook, and file.

## Skill

A reusable structured-extraction template defined in configuration. A skill includes a prompt, optional system prompt and LLM override, and an `output_schema`.

## Source

A plugin that fetches `Item` instances from somewhere external, such as RSS, scraping, search, Reddit, or Hacker News.

## Stage spec

One pipeline stage declaration in YAML. Stage specs can be bare strings like `- dedup` or single-key mappings like `- summarize: { prompt: ... }`.

## Structured output

The JSON-shaped data returned by a skill extraction. It ends up on `Item.structured` and is validated against the skill's schema through the provider layer.

## Tick

One scheduled execution of `Runner.run_feed`. Retries with bounded backoff happen inside a tick; failures that escape the tick increment `consecutive_failures`.

## Trace ID

An 8-character hex ID bound to structlog context for one feed run. It lets you grep or query all log lines emitted by the same tick.
