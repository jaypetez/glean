# SearXNG configuration

This directory holds the configuration for the optional self-hosted
SearXNG metasearch service. It's mounted into the SearXNG container at
`/etc/searxng/` when the `searxng` service is uncommented in `docker-compose.yml`.

See [docs/getting-started/search.md](../docs/getting-started/search.md) for the
full setup guide.

## Files

- `settings.yml`  main SearXNG config. Uses `use_default_settings: true` to
  inherit ~2000 lines of upstream defaults; only overrides what matters.

## Customization

- **Add more engines:** see https://docs.searxng.org/admin/settings/settings_engine.html
- **Engine reliability:** prefer DuckDuckGo, Brave, Mojeek, Startpage. Avoid
  Google direct (CAPTCHAs more often than via Startpage).
- **Private vs public:** keep `limiter: false` and `public_instance: false`.
  These suppress bot protection and public-facing features that aren't needed
  for a single-user setup.
