# 03 — GitHub releases → Slack (no LLM, fast start)

A lean glean example that watches a curated set of GitHub release feeds and posts a digest of new releases to Slack every 6 hours. It runs only the `glean` container—no Ollama sidecar—because release titles are usually already self-describing.

## Requirements

- Docker 24+ with `docker compose` v2
- `curl` (the setup script uses it to probe `healthz`)
- A Slack incoming webhook URL
- No Ollama container, no model pull, and no ~10 GB local LLM footprint

## One-shot setup

```bash
./setup.sh
```

```powershell
./setup.ps1
```

The setup script copies `.env.example` to `.env`, validates `SLACK_WEBHOOK_URL`, starts `glean-ex03-glean`, waits for `http://127.0.0.1:9093/healthz`, and runs a dry-run of `github-releases`.

Because this example keeps `bootstrap: skip-and-mark`, the dashboard stays empty until one of the tracked repos publishes a new release after setup.

## Getting a Slack webhook URL

1. Visit [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** → **From scratch**.
2. Add the **Incoming Webhooks** feature and toggle it **ON**.
3. Click **Add New Webhook to Workspace**, pick a channel, and copy the resulting URL into `.env` as `SLACK_WEBHOOK_URL=...`.

## What the feed does

| Setting | Value |
|---------|-------|
| Schedule | `every 6h` |
| Sources | GitHub `releases.atom` feeds for `python/cpython`, `fastapi/fastapi`, `sveltejs/svelte`, `docker/compose`, and `jaypetez/glean` |
| Pipeline | `dedup → digest` |
| Sinks | `slack` webhook + `dashboard` (keeps the last 50 digests) |
| Bootstrap | `skip-and-mark` |
| Render defaults | `style: plain`, `link_preview: false`, `max_items: 8` |

## Customizing the repo list

Edit the five `url:` lines under `sources:` in [`feeds.yaml`](./feeds.yaml) (currently lines 25-35). Any GitHub repo with a Releases page can be turned into an Atom feed by appending `.atom` to the releases URL:

```text
https://github.com/OWNER/REPO/releases.atom
```

Example: `https://github.com/pallets/flask/releases.atom`

After changing the list, restart glean:

```bash
docker compose -f docker-compose.yml restart glean
```

## Viewing digests in the browser

This example also enables the [`dashboard`](../../docs/how-to/sinks/dashboard.md) sink, so you can browse recent release digests locally even though delivery goes to Slack. On the first run, expect an empty list until a tracked repo ships a new release because bootstrap is `skip-and-mark`.

1. Get the API key from the container logs:

   ```bash
   docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY | head -1
   ```

2. Open <http://127.0.0.1:9093/> in your browser.
3. Paste the API key when prompted, then open the **Digests** tab.

## Adding LLM changelog summarization

The bottom of [`feeds.yaml`](./feeds.yaml) includes a commented alternative that adds `defaults.llm` plus a `summarize` stage for release body text. If you enable it, also add an `ollama` service to [`docker-compose.yml`](./docker-compose.yml) before restarting—the default example intentionally skips that container to keep startup fast.

## Teardown

```bash
./teardown.sh
```

```powershell
./teardown.ps1
```

This stops the stack, removes its volumes, and deletes the local `data/` directory plus `.env`.

## Going further

- [Slack setup guide](../../docs/how-to/sinks/slack.md)
- [Dashboard sink guide](../../docs/how-to/sinks/dashboard.md)
- [Feed config reference](../../docs/config/feeds.md#slack)
- [Main project README](../../README.md)
