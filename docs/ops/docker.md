# Docker

## docker compose

```bash
docker compose up -d          # start
docker compose logs -f glean  # follow logs
docker compose down           # stop
```

## State

State lives at `/data/state.db` (SQLite). Mount a volume to persist across container restarts.

## Security model

Glean is a single-user service: the API key is the sole gate for the Web UI and REST API, and anyone with the key can manage feeds. Do not set `GLEAN_DISABLE_AUTH` on a public port, shared host, or untrusted network; reserve it for loopback-only tests or a trusted reverse proxy that enforces its own auth.

Protect the mounted data directory with `chmod 700 /data`. The verifier at `/data/api_key` must remain `chmod 600`; startup warns if the data directory is world-accessible and fails if a verifier is not private. On first boot, bootstrap the UI with:

```bash
docker logs glean | grep GLEAN_INITIAL_API_KEY
```

If you expose the UI/API outside localhost, put it behind a reverse proxy with TLS, keep port 9090 private, and enforce any extra auth and rate limits at the proxy.

## Health endpoint

`GET /healthz` on port 9090 returns 200 if the scheduler is running and the DB is reachable.

## Bootstrap behavior

On first run of any new feed, current items are indexed without sending — only new items go out on the next tick. Override with `bootstrap: send-last-N`.

## Logs

- Dev: structured `key=value` to stderr
- Production: set `LOG_FORMAT=json` for JSON output
