---
title: Debug a Feed — Agent Runbook
description: Mechanical step-by-step for diagnosing why a glean feed isn't sending.
---

# Debug a feed that isn't sending

Use this when a feed fetches items but nothing reaches a sink, or when a scheduled run behaves differently from `glean test-feed`.

## Step 1 — Verify the source is reachable

Use the same SSRF validator glean uses before outbound HTTP. Replace the example URL with the source URL from `feeds.yaml`:

```bash
docker exec -i glean python - <<'PY'
import asyncio
import httpx
from glean.security.ssrf import validate_url

async def main() -> None:
    url = validate_url("https://example.com/feed.xml")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        print(f"STATUS={response.status_code} URL={response.url}")
        print(response.text[:200].replace("\n", " "))

asyncio.run(main())
PY
```

Expected output:

```text
STATUS=200 URL=https://example.com/feed.xml
<?xml version="1.0" ...
```

If `validate_url()` raises, the rejection is intentional. Check whether you're pointing a public-only field at a private or loopback address.

## Step 2 — Check the bootstrap state

If your agent has the MCP server loaded, query these two statements with the `query_db` tool:

```sql
SELECT feed, bootstrapped, consecutive_failures, alert_active, last_error
FROM feed_runs
WHERE feed = '<name>';

SELECT COUNT(*) AS seen_count, COALESCE(SUM(sent), 0) AS sent_count
FROM seen_items
WHERE feed = '<name>';
```

Otherwise, query the SQLite DB directly inside the container:

```bash
docker exec -i glean python - <<'PY'
import sqlite3

feed = "<name>"
connection = sqlite3.connect("/data/state.db")
connection.row_factory = sqlite3.Row
try:
    for sql in (
        "SELECT feed, bootstrapped, consecutive_failures, alert_active, last_error FROM feed_runs WHERE feed = ?",
        "SELECT COUNT(*) AS seen_count, COALESCE(SUM(sent), 0) AS sent_count FROM seen_items WHERE feed = ?",
    ):
        print(sql)
        for row in connection.execute(sql, (feed,)):
            print(dict(row))
finally:
    connection.close()
PY
```

Interpretation:

- `bootstrapped = 0` means the next non-dry run in the default `skip-and-mark` mode will index items and send nothing.
- `bootstrapped = 1` means the baseline already exists; keep debugging.
- `seen_count > 0` with `sent_count > 0` usually means dedup is doing its job.

## Step 3 — Tail the feed's `trace_id` logs

If the container is running with `LOG_FORMAT=json`, use `jq`:

```bash
docker logs glean 2>&1 | jq -c 'select(.feed=="<name>")' | tail -50
```

Find the `trace_id` from the `run_feed.start` line, then isolate that one run:

```bash
docker logs glean 2>&1 | jq -c 'select(.trace_id=="<trace_id>")'
```

If logs are in the default console format, grep works too:

```bash
docker logs glean 2>&1 | grep "feed=<name>" | tail -50
docker logs glean 2>&1 | grep "trace_id=<trace_id>"
```

Useful events from `Runner.run_feed` include `run_feed.start`, `bootstrap_skip`, `no_new_items`, `nothing_to_send`, `run_feed.failed`, and `run_feed.complete`.

## Step 4 — Reproduce locally

Use one or both of these reproduction paths:

```bash
make e2e
uv run glean test-feed <name> -c feeds.example.yaml --log-level DEBUG
```

`make e2e` verifies the full mocked Docker path. `uv run glean test-feed ...` reproduces one feed locally with verbose logs. If you need to exercise the live sink path and write state, rerun the second command with `--send`.

## Common findings + fixes

- `no_new_items` but you expected items: check bootstrap and dedup first — see [Dedup and bootstrap](../concepts/dedup-bootstrap.md).
- Repeated `429` errors: the source or provider is rate-limiting you. Slow the schedule first; raise `failure.alert_after` only to reduce alert noise.
- `validate_url` rejection: the URL points at a private or loopback address. That allowlist is intentional.
- The source returns items but summarize or digest fails: check the effective LLM config and remember the precedence is skill → source → feed → defaults.
- Dry-runs repeatedly show `skipped: bootstrap`: `glean test-feed` does not write state. Run a real tick or `glean send-now <name>` to establish the baseline.
