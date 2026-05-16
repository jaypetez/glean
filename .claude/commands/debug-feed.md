Debug why feed `$ARGUMENTS` isn't sending.

Follow the runbook at `docs/agents/debug-feed.md` step-by-step. Use the MCP tools where possible:
- `query_db` to inspect `seen_items` and `feed_runs` for this feed
- `get_logs feed=$ARGUMENTS lines=200` to tail the feed's trace_id logs
- `validate_config` if the YAML is suspect

Report findings as: (1) what state shows, (2) what logs show, (3) hypothesis, (4) fix.
