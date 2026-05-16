# scripts/

Utility scripts for development, docs generation, and agent tooling.

| Script | Purpose | Invocation |
|--------|---------|------------|
| `dump_openapi.py` | Export FastAPI OpenAPI JSON | `make docs-api` |
| `dump_schema.py` | Export feeds.yaml JSON Schema | `make docs-schema` |
| `normalize_utf8.py` | Fix Unicode in generated docs | called by `make docs-cli` |
| `prepend_frontmatter.py` | Add MkDocs frontmatter to generated pages | called by `make docs-cli` |
| `new_plugin.py` | Scaffold a new plugin (source/sink/llm/search) | `uv run python scripts/new_plugin.py source my_source` |
| `mcp_server.py` | MCP server exposing dev tools to Claude Code/Cursor when the companion MCP tooling is present | wired via `.mcp.json` in MCP-enabled setups |

All scripts assume `uv` and the project's Python env. Run from the repo root.
