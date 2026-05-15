---
title: "How to monitor glean - glean"
description: "Use health checks, JSON logs, and log shipping for day-2 operations."
---

# Monitor glean

**Goal:** Check service health, parse production logs, and forward operational signals to your logging stack.

**You need:**

- Access to port `9090` on loopback or through your reverse proxy.
- `curl` and, optionally, `jq` for health checks.
- A log collector such as Loki, Promtail, Filebeat, or an ELK-compatible agent.

## Steps

1. Poll the unauthenticated health endpoint.

   ```bash
   curl -fsS http://127.0.0.1:9090/healthz | jq
   ```

   A healthy response has this shape:

   ```json
   {
     "status": "ok",
     "db": "ok",
     "scheduler": "running",
     "version": "1.3.0",
     "uptime_s": 12345
   }
   ```

   Alert when `status` is not `ok`, `db` is not `ok`, or `scheduler` is `stopped` for a daemon deployment. API-only test apps can report `"scheduler":"n/a"`.

2. Emit JSON logs in production.

   ```env
   LOG_FORMAT=json
   LOG_LEVEL=INFO
   ```

   Restart after changing `.env`:

   ```bash
   docker compose up -d glean
   ```

3. Inspect JSON logs locally.

   ```bash
   docker compose logs --no-log-prefix glean | jq -c 'select(.level == "warning" or .level == "error")'
   ```

   `structlog` events include keys such as `event`, `level`, `timestamp`, `logger`, `feed`, counts, durations, and sanitized error text.

4. Ship logs to Loki.

   A typical Promtail Docker job keeps the JSON line intact and lets Loki parse fields at query time:

   ```yaml
   scrape_configs:
     - job_name: glean
       docker_sd_configs:
         - host: unix:///var/run/docker.sock
       relabel_configs:
         - source_labels: [__meta_docker_container_name]
           regex: /glean
           action: keep
       pipeline_stages:
         - json:
             expressions:
               level: level
               event: event
               feed: feed
   ```

5. Ship logs to ELK.

   Configure Filebeat or Elastic Agent to read the Docker container log and decode JSON:

   ```yaml
   filebeat.inputs:
     - type: filestream
       id: glean-container
       paths:
         - /var/lib/docker/containers/*/*.log
       parsers:
         - container: {}
         - ndjson:
             target: ""
             add_error_key: true
   ```

## Verify

Run:

```bash
curl -fsS http://127.0.0.1:9090/healthz | jq -e '.status == "ok" and .db == "ok"'
docker compose logs --no-log-prefix glean --tail=20 | jq -c .
```

Expected output is exit code `0` from the health check and JSON-parsable log lines after `LOG_FORMAT=json` is enabled.

## Next steps

- Alert on repeated feed failures and health degradation.
- Keep `/healthz` reachable to your monitor but not publicly exposed without the same access controls as the UI.
- Native Prometheus metrics are on the roadmap. Until then, use `/healthz` plus structured logs.
