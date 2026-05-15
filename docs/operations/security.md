---
title: "Security Model — glean Operations"
description: Threat model, safe deployment settings, hardening, and vulnerability reporting for glean.
---

# Security Model and Deployment Guide

This page describes the security model for `glean` v1.1.x and the minimum safe
settings for self-hosted deployments.

!!! success "Security checklist"
    - [ ] Port 9090 is on loopback or behind a reverse proxy
    - [ ] API key is in `.env`, not hardcoded
    - [ ] `/data` is `chmod 700`
    - [ ] `/data/api_key` is `chmod 600`
    - [ ] TLS is terminated at the proxy
    - [ ] `GLEAN_DISABLE_AUTH` is NOT set
    - [ ] Latest patch version (run `glean migrate` after upgrade)

## Threat model

`glean` is a single-user service. The Web UI and REST API share one trust
boundary: the API key. Anyone with the key can manage feeds, read status, run
feeds, and rotate the key.

Trusted components:

- The container operator.
- The host machine and private Docker/network configuration.
- The mounted `/data` volume, when file permissions are private.

Untrusted components:

- External HTTP responses from RSS, scraper, and search sources.
- LLM model outputs, including local and hosted providers.
- Sink endpoints such as Telegram, Discord, Slack, ntfy, and webhooks.

## Network exposure

Inside the container, `glean` binds to `0.0.0.0:9090` so Docker can publish the
Web UI, REST API, and `/healthz` endpoint. Do not publish that port on a public
interface.

When running locally, publish the port on loopback only:

```yaml
services:
  glean:
    ports:
      - "127.0.0.1:9090:9090"
```

Equivalent `docker run` form:

```bash
docker run -p 127.0.0.1:9090:9090 ghcr.io/jaypetez/glean:v1.1.0
```

For remote access, keep port 9090 private and put `glean` behind a reverse proxy
that terminates TLS and adds your organization's access controls. Never expose
port 9090 publicly without authentication and TLS.

<a id="nginx-example"></a>
For nginx, use the dedicated [nginx reverse proxy how-to](../how-to/ops/nginx.md).

<a id="caddy-example"></a>
For Caddy, use the dedicated [Caddy reverse proxy how-to](../how-to/ops/caddy.md).

<a id="traefik-example"></a>
For Traefik v3, use the dedicated [Traefik reverse proxy how-to](../how-to/ops/traefik.md).

## API key bootstrap and rotation

On first boot, if no verifier exists and `GLEAN_API_KEY` is not set, `glean`
generates an initial key and logs it once to stderr:

```bash
docker logs glean | grep GLEAN_INITIAL_API_KEY
```

Paste that key into the Web UI, then store it in a password manager or rotate it.
The unauthenticated initialization endpoint does not return the plaintext key.

For production, set a fixed key in `.env` and restart the container:

```env
GLEAN_API_KEY=<your-32-char-key>
```

For rotation steps, use the dedicated [API key rotation how-to](../how-to/ops/rotate-key.md).

You can disable API authentication entirely with:

```env
GLEAN_DISABLE_AUTH=1
```

Startup emits a warning when this is set. Never use `GLEAN_DISABLE_AUTH=1` in
production, on a shared host, or on any network with untrusted clients.

## File permissions

Protect the bind-mount root and the API key verifier:

```bash
chmod 700 /data
chmod 600 /data/api_key
```

If your host path is `./data`, apply the same modes to that path before starting
Docker. Startup warns when the data directory or verifier is world-accessible and
fails if `/data/api_key` is not mode `0o600` (`chmod 600`).

## Built-in protections from the v1.1.x audit

- **First-run key disclosure fix (PR #102 / issue #82):** `/api/v1/initialize`
  no longer returns the plaintext API key. The generated key is logged once.
- **SSRF allowlist and blocklist guard (PR #106 / issue #83):** outbound URLs
  are validated against a blocklist for RFC1918, link-local, loopback,
  multicast, and cloud-metadata addresses. The guarded `httpx` transport
  revalidates after DNS resolution and redirects to defeat DNS rebinding.
- **Prompt-injection defense (PR #103 / issue #84):** scraped content is wrapped
  in `<UNTRUSTED_CONTENT>` delimiters, prompts include shared system guards, and
  summaries/digest intros pass through an output filter for suspected injection.
- **Auth and verifier hardening (PR #104 / issue #87):** disabling auth logs a
  startup warning, world-accessible data paths warn, and verifier files must be
  private.
- **SQLite hardening (PR #99 / issue #88):** `PRAGMA secure_delete=ON`,
  `foreign_keys=ON`, and `trusted_schema=OFF` are enabled when the state store
  opens. Database paths are constrained to `/data` unless `GLEAN_DB_ROOT` is set.
- **Container hardening (PR #100 / issue #92):** the image was refreshed to a
  Debian 13 base, packages are upgraded during build, and active HIGH/CRITICAL
  CVEs are gated by Trivy.
- **Secret scrubbing (PR #101 / issue #95):** API keys are redacted from errors,
  status APIs, CLI output, ops alerts, and logs. Patterns include `sk-...`,
  `Bearer ...`, `token=...`, and Telegram `/bot...` tokens.
- **Response body cap (PR #105 / issue #90):** RSS and scraper fetches stream
  responses with a default 10 MiB cap to reduce memory-exhaustion risk. Override
  per source with `max_response_bytes` only when you trust the source.
- **Telegram link safety:** rendered Telegram links are limited to `http://` and
  `https://` URLs before they are emitted in `<a href>` tags.

## Secret management

Use `.env` for all secrets, including `TELEGRAM_BOT_TOKEN`, `BRAVE_API_KEY`,
`TAVILY_API_KEY`, `SERPER_API_KEY`, `EXA_API_KEY`, and `GLEAN_API_KEY`. Commit
`.env.example` as the template and keep `.env` private.

Do not put secrets directly in `feeds.yaml`; it is designed to be safe to commit.
Reference secrets and per-environment values through interpolation:

```yaml
sinks:
  - type: telegram
    chat_id: ${TELEGRAM_CHAT_AI}
```

Cloud search providers may log queries and enforce their own key policies. Scope
Brave, Tavily, Serper, and Exa keys with IP allowlists where the provider
supports it, and rotate keys after any suspected leak.

## RSS and scraper considerations

The pipeline treats source URLs and content as untrusted. The SSRF guard checks
URLs before fetching and after DNS resolution, and scraped content is delimited
before it reaches the LLM.

Your LLM provider may still log prompts and feed content. Use Ollama or another
local provider for sensitive feeds. Likewise, choose Telegram, Discord, Slack,
ntfy, and webhook destinations carefully; `glean` will deliver to whatever sink
you configure.

## Reporting vulnerabilities

Do not open public issues for vulnerabilities. Report privately through GitHub
Private Vulnerability Reporting, or email `jayson@shoe4africa.org` with
`[glean security]` in the subject.

Use a 90-day disclosure window unless we agree otherwise. We credit reporters in
release notes unless they prefer to remain anonymous.

## Multi-user and RBAC roadmap

`glean` is currently single-user with one shared API key. Multi-user support with
JWTs and roles is planned for the v2.x roadmap and will be tracked by a dedicated
issue.

For multi-tenant deployments today, run separate containers. Give each tenant a
separate config, data volume, API key, and sink credentials.

## Cosign verification and SBOM

Release images are signed keylessly with Sigstore cosign. Verify a release image
before deploying it:

```bash
cosign verify ghcr.io/jaypetez/glean:v1.1.0 \
  --certificate-identity-regexp 'https://github.com/jaypetez/glean/.github/workflows/release.yml@.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

Release builds also attach an SBOM artifact. Use the CycloneDX or SPDX SBOM
attached to the release you deploy for dependency inventory and vulnerability
review.
