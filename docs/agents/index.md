---
title: Agent Runbooks — glean
description: Step-by-step recipes for AI coding agents working on glean.
---

# Agent Runbooks

This section is for AI coding agents (Claude Code, Cursor, Copilot, Aider, OpenCode, Devin, etc.) working on glean. It contains task-focused recipes that work mechanically — no inference required.

## Pre-work
- [Session checklist](new-session-checklist.md) — read this first

## Common tasks
- [Debug a feed that isn't sending](debug-feed.md)
- [Add a new plugin (source/sink/LLM/search)](add-plugin.md)
- [Cut a release](release.md)

## Slash commands
Claude Code slash commands live in `.claude/commands/`:
- `/check` — run `make check` and iteratively fix lint, type, and test failures.
- `/add-source` — scaffold and implement a new source plugin, tests, docs, and PR.
- `/add-sink` — scaffold and implement a new sink plugin, tests, docs, and PR.
- `/add-llm` — scaffold and implement a new LLM provider and its protocol methods.
- `/debug-feed` — follow the feed debugging runbook with MCP tooling and report state, logs, hypothesis, and fix.
- `/release` — follow the release runbook to cut a versioned release safely.
- `/triage-issue` — inspect a GitHub issue, reproduce when needed, label it, and comment with next steps.

## Reference
- [Common pitfalls (do NOT do these)](pitfalls.md)
- [Key files map](key-files.md)
- [Glossary of glean-specific terms](../reference/glossary.md)
