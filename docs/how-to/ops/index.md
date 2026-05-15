# Operations How-to Guides

Task-focused guides for running `glean` in production.

## Reverse proxies

- [nginx](nginx.md) - terminate TLS with Let's Encrypt, stream SSE, and add proxy rate limits.
- [Caddy](caddy.md) - use Caddy auto-HTTPS with an SSE-friendly reverse proxy.
- [Traefik v3](traefik.md) - route to the `glean` service with Docker labels and a TLS resolver.

## Day-2 operations

- [Backup and restore](backup.md) - back up SQLite online, snapshot `/data/`, and restore safely.
- [Upgrade](upgrade.md) - pull a new image, run migrations, verify, and roll back with a backup.
- [Monitoring](monitoring.md) - check `/healthz`, parse JSON logs, and ship logs to Loki or ELK.
- [Rotate the API key](rotate-key.md) - rotate from the UI or regenerate `/data/api_key` as a fallback.
- [Reset one feed](reset-feed.md) - clear feed state, reset bootstrap, or run one off-schedule send.
