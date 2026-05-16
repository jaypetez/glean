---
title: Key Files Map — Agent Runbook
description: A map of glean's most-edited files for AI agents.
---

# Key Files Map

When you're debugging or adding features, these are the files that matter:

## Pipeline core
- `src/glean/pipeline/engine.py::Runner.run_feed` — the feed execution loop
- `src/glean/pipeline/stages.py` — dedup, rank, summarize, apply_skill, digest
- `src/glean/sources/base.py::Item` — frozen dataclass; never mutate, use `replace()`

## Config
- `src/glean/config/schema.py` — Pydantic models; read before touching YAML
- `src/glean/config/loader.py` — env var interpolation
- `src/glean/config/schedule.py` — schedule string parsing

## State
- `src/glean/state/store.py` — aiosqlite wrapper; PRAGMAs set on open
- `src/glean/state/migrations/` — yoyo SQL migrations; one file per change

## Security boundaries
- `src/glean/security/ssrf.py::validate_url` — call before every outbound HTTP
- `src/glean/security/scrub.py::scrub` — call on any text headed to logs/alerts
- `src/glean/llm/output_filter.py::filter_llm_output` — apply to summarize/digest output

## Plugin registries (4)
- `src/glean/sources/registry.py::_import_builtins`
- `src/glean/sinks/registry.py::_import_builtins`
- `src/glean/llm/registry.py::_import_builtins`
- `src/glean/search/registry.py::_import_builtins`

## Test infrastructure
- `tests/conftest.py::_isolate_env` — autouse fixture stripping secret env vars
- `tests/conftest.py::tmp_db` — per-test SQLite fixture
- `tests/e2e/conftest.py` — Docker compose stack lifecycle
