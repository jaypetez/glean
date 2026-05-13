# Docker

## docker compose

```bash
docker compose up -d          # start
docker compose logs -f glean  # follow logs
docker compose down           # stop
```

## State

State lives at `/data/state.db` (SQLite). Mount a volume to persist across container restarts.

## Health endpoint

`GET /healthz` on port 9090 returns 200 if the scheduler is running and the DB is reachable.

## Bootstrap behavior

On first run of any new feed, current items are indexed without sending — only new items go out on the next tick. Override with `bootstrap: send-last-N`.

## Logs

- Dev: structured `key=value` to stderr
- Production: set `LOG_FORMAT=json` for JSON output
