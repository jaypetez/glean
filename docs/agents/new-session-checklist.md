---
title: New Session Checklist — Agent Runbook
description: 6-step pre-work checklist for AI agents starting a glean coding session.
---

# New Session Checklist

Run these 6 steps before touching any code:

1. **Sync main**: `git checkout main && git pull --rebase origin main`
2. **Read context**: skim `AGENTS.md` (~2 min) — it's the cross-tool primer
3. **Check pitfalls**: skim `docs/agents/pitfalls.md` (~1 min)
4. **If adding a plugin**: read `docs/plugins/<type>.md` for the relevant layer
5. **Verify clean state**: `make check` (~2 min) — if this fails before your edits, record the baseline failure before proceeding
6. **Branch**: `git checkout -b <type>/<slug>` where `<type>` ∈ `{feat, fix, docs, chore}`

## Then start work

For most tasks: edit → `uv run ruff check --fix src tests && uv run mypy src` → iterate. Run full `make check` before commit.

For new plugins: if your checkout includes the PR2 scaffold helper, use `make new-plugin LAYER=source NAME=my-source` to scaffold. Otherwise start from the 30-second scaffold in `docs/plugins/index.md`.
