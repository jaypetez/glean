---
title: "How to put glean behind Caddy - glean"
description: "Use Caddy auto-HTTPS as a reverse proxy for glean."
---

# Put glean behind Caddy

**Goal:** Expose `glean` at an HTTPS hostname with Caddy's automatic certificate management while keeping port `9090` private.

**You need:**

- A running `glean` container with `127.0.0.1:9090:9090` or an equivalent private network path.
- DNS for `glean.example.com` pointing at the Caddy host.
- Caddy 2 installed and able to bind ports `80` and `443`.

## Steps

1. Keep direct app access on loopback.

   ```yaml
   services:
     glean:
       ports:
         - "127.0.0.1:9090:9090"
   ```

2. Add a Caddyfile for the site.

   ```caddyfile
   {
       email admin@example.com
   }

   glean.example.com {
       encode zstd gzip

       reverse_proxy 127.0.0.1:9090 {
           header_up Host {host}
           header_up X-Forwarded-Proto {scheme}
           header_up X-Forwarded-For {remote_host}
           flush_interval -1

           transport http {
               read_timeout 1h
               write_timeout 1h
           }
       }
   }
   ```

   Caddy obtains and renews certificates automatically. `flush_interval -1` keeps SSE responses streaming promptly, and WebSocket upgrades are handled automatically.

3. Add optional basic auth if you need a second gate in front of the API key.

   Generate a hash first:

   ```bash
   caddy hash-password
   ```

   Then add it inside the site block:

   ```caddyfile
   basicauth {
       operator $2a$14$replace-with-caddy-hash
   }
   ```

4. Validate and reload Caddy.

   ```bash
   sudo caddy validate --config /etc/caddy/Caddyfile
   sudo systemctl reload caddy
   ```

## Verify

Run:

```bash
curl -fsS https://glean.example.com/healthz
curl -I https://glean.example.com/
```

Expected output includes `"status":"ok"` from `/healthz`. Caddy logs should not show upstream connection errors.

## Next steps

- Keep `GLEAN_DISABLE_AUTH` unset in production.
- Use Caddy access logs or your platform logs for audit trails.
- Review [API key rotation](rotate-key.md) before handing access to another operator.
