---
title: "How to rotate the API key - glean"
description: "Rotate the single-user API key from the UI or recovery fallback."
---

# Rotate the API key

**Goal:** Replace the single-user API key and update every client that talks to the Web UI or REST API.

**You need:**

- The current API key, unless you are using the recovery fallback.
- Access to the Web UI or shell access to the Docker host.
- A secure place to store the new key, such as a password manager or `.env` secret store.

!!! warning "Clients break immediately"
    Rotation invalidates the old key as soon as the new key is saved. Browser tabs, CLI scripts, API clients, and automation will fail until they use the new key.

## Steps

1. Prefer the Web UI flow when you can still sign in.

   1. Open the Web UI.
   2. Go to **Settings -> API Key -> Rotate API key**.
   3. Confirm the warning.
   4. Copy the new key immediately; it is shown once.
   5. Paste the new key into every browser, script, and secret store that calls `glean`.

2. If `GLEAN_API_KEY` is set in `.env`, rotate it externally instead.

   ```env
   GLEAN_API_KEY=<new-secret-key>
   ```

   Then restart:

   ```bash
   docker compose up -d glean
   ```

3. Use the file fallback only when you cannot sign in and `GLEAN_API_KEY` is not set.

   Make sure `GLEAN_API_KEY` is unset in `.env`; an environment key takes precedence and prevents regeneration.

   ```bash
   docker compose down
   rm -f ./data/api_key
   docker compose up -d glean
   docker logs glean 2>&1 | grep GLEAN_INITIAL_API_KEY
   ```

   If your deployment uses a named volume, delete `/data/api_key` from that volume instead of `./data/api_key`. The regenerated plaintext key is logged once.

4. Store the new key and remove any temporary terminal scrollback or screenshots that captured it.

## Verify

Run:

```bash
curl -fsS -H "X-Glean-Api-Key: <new-key>" http://127.0.0.1:9090/api/v1/feeds >/dev/null
curl -sS -i -H "X-Glean-Api-Key: <old-key>" http://127.0.0.1:9090/api/v1/feeds
```

Expected output: the new key succeeds, and the old key fails with an authentication error.

## Next steps

- Update monitoring, scripts, and browser storage with the new key.
- Take a fresh backup after rotation so `/data/api_key` matches the current deployment.
- Review the [security checklist](../../operations/security.md) for file permissions and auth settings.
