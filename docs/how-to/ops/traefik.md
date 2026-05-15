---
title: "How to put glean behind Traefik v3 - glean"
description: "Route Traefik v3 to glean with Docker labels and a TLS resolver."
---

# Put glean behind Traefik v3

**Goal:** Route HTTPS traffic from Traefik v3 to the `glean` container while keeping the app's internal port private.

**You need:**

- Docker Compose with Traefik v3 on the same Docker network as `glean`.
- DNS for `glean.example.com` pointing at the Traefik host.
- A Traefik ACME certificate resolver, named `letsencrypt` in the example below.

## Steps

1. Add or confirm a Traefik service with `web` and `websecure` entry points.

   ```yaml
   services:
     traefik:
       image: traefik:v3.0
       command:
         - --providers.docker=true
         - --providers.docker.exposedbydefault=false
         - --entrypoints.web.address=:80
         - --entrypoints.websecure.address=:443
         - --certificatesresolvers.letsencrypt.acme.email=admin@example.com
         - --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json
         - --certificatesresolvers.letsencrypt.acme.httpchallenge=true
         - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
       ports:
         - "80:80"
         - "443:443"
       volumes:
         - /var/run/docker.sock:/var/run/docker.sock:ro
         - traefik-letsencrypt:/letsencrypt
       networks:
         - glean
   ```

2. Put labels on the `glean` service.

   ```yaml
   services:
     glean:
       image: ghcr.io/jaypetez/glean:latest
       env_file:
         - .env
       volumes:
         - ./data:/data
         - ./feeds.yaml:/etc/glean/feeds.yaml:ro
       expose:
         - "9090"
       labels:
         - traefik.enable=true
         - traefik.http.routers.glean.rule=Host(`glean.example.com`)
         - traefik.http.routers.glean.entrypoints=websecure
         - traefik.http.routers.glean.tls=true
         - traefik.http.routers.glean.tls.certresolver=letsencrypt
         - traefik.http.routers.glean.service=glean
         - traefik.http.services.glean.loadbalancer.server.port=9090
         - traefik.http.middlewares.glean-ratelimit.ratelimit.average=10
         - traefik.http.middlewares.glean-ratelimit.ratelimit.burst=60
         - traefik.http.routers.glean.middlewares=glean-ratelimit@docker
       networks:
         - glean
   ```

   Traefik handles WebSocket upgrades and SSE streaming without extra response-buffer settings. The service label points Traefik at the container's internal `9090` port.

3. Define the shared network and certificate volume if they do not already exist.

   ```yaml
   volumes:
     traefik-letsencrypt:

   networks:
     glean:
       driver: bridge
   ```

4. Start or reload the stack.

   ```bash
   docker compose up -d traefik glean
   ```

## Verify

Run:

```bash
curl -fsS https://glean.example.com/healthz
curl -I https://glean.example.com/
docker compose logs traefik --tail=100
```

Expected output includes `"status":"ok"`, and Traefik logs should show a router named `glean@docker` using the `websecure` entry point.

## Next steps

- Add SSO, IP allowlists, or basic auth middleware if your deployment needs another access layer.
- Keep the `glean` service off public host ports unless it is bound to loopback only.
- Review the [security checklist](../../operations/security.md) after changing labels.
