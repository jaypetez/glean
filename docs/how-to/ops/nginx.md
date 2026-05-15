---
title: "How to put glean behind nginx - glean"
description: "Terminate TLS with nginx, Certbot, SSE/WebSocket headers, and rate limits."
---

# Put glean behind nginx

**Goal:** Expose the Web UI, REST API, SSE events, and `/healthz` over HTTPS while keeping the app server on `127.0.0.1:9090`.

**You need:**

- A running `glean` container with port `9090` published on loopback only.
- DNS for `glean.example.com` pointing at the host.
- nginx and Certbot installed on the host.
- Shell access with permission to edit nginx config and reload the service.

## Steps

1. Keep the container private.

   ```yaml
   services:
     glean:
       ports:
         - "127.0.0.1:9090:9090"
   ```

2. Install nginx and Certbot.

   ```bash
   sudo apt update
   sudo apt install nginx certbot python3-certbot-nginx
   ```

3. Issue the Let's Encrypt certificate.

   If this is the first certificate for the host, use Certbot standalone while port `80` is free:

   ```bash
   sudo systemctl stop nginx
   sudo certbot certonly --standalone -d glean.example.com
   sudo systemctl start nginx
   ```

4. Create `/etc/nginx/sites-available/glean`.

   ```nginx
   limit_req_zone $binary_remote_addr zone=glean_api:10m rate=10r/s;
   limit_req_zone $binary_remote_addr zone=glean_sensitive:10m rate=5r/m;

   map $http_upgrade $connection_upgrade {
       default upgrade;
       '' close;
   }

   server {
       listen 80;
       server_name glean.example.com;

       location /.well-known/acme-challenge/ {
           root /var/www/html;
       }

       location / {
           return 301 https://$host$request_uri;
       }
   }

   server {
       listen 443 ssl http2;
       server_name glean.example.com;

       ssl_certificate /etc/letsencrypt/live/glean.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/glean.example.com/privkey.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_prefer_server_ciphers off;

       add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

       location / {
           limit_req zone=glean_api burst=60 nodelay;

           proxy_pass http://127.0.0.1:9090;
           proxy_http_version 1.1;

           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto https;

           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection $connection_upgrade;

           proxy_read_timeout 3600s;
           proxy_send_timeout 3600s;
           proxy_buffering off;
           proxy_cache off;
       }

       location = /api/v1/auth/rotate {
           limit_req zone=glean_sensitive burst=3 nodelay;

           proxy_pass http://127.0.0.1:9090;
           proxy_http_version 1.1;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto https;
           proxy_read_timeout 3600s;
           proxy_send_timeout 3600s;
           proxy_buffering off;
           proxy_cache off;
       }
   }
   ```

   The `limit_req_zone` and `map` directives must be loaded in nginx's `http` context before the `server` blocks. Debian and Ubuntu include `sites-enabled/*` there by default; on RHEL, Alpine, or custom nginx builds, place this block in whichever file your `nginx.conf` includes from `http`.

   The `Upgrade` and `Connection` headers keep WebSockets working. `proxy_buffering off` keeps Server-Sent Events streaming instead of batching.

5. Enable the site and reload nginx.

   ```bash
   sudo ln -s /etc/nginx/sites-available/glean /etc/nginx/sites-enabled/glean
   sudo nginx -t
   sudo systemctl reload nginx
   ```

## Verify

Run:

```bash
curl -fsS https://glean.example.com/healthz
curl -I https://glean.example.com/
```

Expected output includes JSON with `"status":"ok"` from `/healthz`, and the root page returns an HTTPS response. Confirm Docker is not publishing a public `0.0.0.0:9090` listener.

## Next steps

- Store the API key in `.env`, not in nginx config.
- Add your organization's SSO, VPN, or basic auth layer at nginx if the host is shared.
- Review the [security model](../../operations/security.md) before exposing remote access.
