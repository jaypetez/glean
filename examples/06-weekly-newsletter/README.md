# 06 — Weekly AI news → email (Mailpit local + real SMTP)

A self-contained glean example that pulls two AI-heavy RSS feeds once a week, ranks and summarizes them with Ollama, and delivers the digest as a styled HTML email.

By default, the email goes to the local **Mailpit** sidecar, so you can inspect every message safely at <http://127.0.0.1:8025> with zero external dependencies. When you are ready, you can swap the SMTP settings to Gmail, Fastmail, or AWS SES and deliver to a real inbox.

Three containers: `glean-ex06-glean`, `glean-ex06-ollama`, and `glean-ex06-mailpit`. All are attached to the private bridge network `glean-ex06`.

## What this example does

- Fetches fresh items from Simon Willison's Atom feed and HN RSS results for `AI`
- Deduplicates items, ranks them for practical AI engineering relevance, and summarizes them with **Ollama** `qwen2.5:7b`
- Renders the digest as **HTML email** via the `email` sink
- Stores recent runs in the built-in `dashboard` sink so you can inspect past digests in the web UI
- Catches every outbound email in **Mailpit** by default so you can test locally before sending to a real inbox

## Requirements

- Docker 24+ with `docker compose` v2
- `curl` (used by the setup scripts for the health check)
- ~10 GB free disk for the Ollama model plus container images

## One-shot setup

```bash
./setup.sh
```

```powershell
./setup.ps1
```

The setup script creates `.env` from `.env.example`, starts Mailpit and Ollama first, waits for Ollama to become healthy, pulls `qwen2.5:7b` if needed, starts `glean-ex06-glean`, waits for <http://127.0.0.1:9096/healthz>, and dry-runs the `weekly-digest` feed.

## Viewing your email

Open <http://127.0.0.1:8025> — Mailpit shows every email glean sends. Click any email to see the full HTML rendering.

## Sending to a real inbox

The shipped `feeds.yaml` is intentionally local-first:

```yaml
      - type: email
        smtp_host: mailpit
        smtp_port: 1025
        smtp_user: ""
        smtp_password: ""
        starttls: false
        from: "glean <glean@localhost>"
        to:
          - me@localhost
```

To use a real provider, keep the rest of the feed the same and replace the SMTP values above with your provider's settings. In every case, also change the recipient line under `to:` to your real inbox.

### Gmail

1. Enable 2-Step Verification on your Google account.
2. Create an App Password for Mail.
3. Edit `.env` with these values:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-16-character-app-password
SMTP_STARTTLS=true
```

Then change this line in `feeds.yaml`:

```yaml
to:
  - you@gmail.com
```

And replace the local Mailpit SMTP fields with the Gmail values above.

### Fastmail

1. Create an app password in Fastmail.
2. Edit `.env` with these values:

```dotenv
SMTP_HOST=smtp.fastmail.com
SMTP_PORT=587
SMTP_USER=you@fastmail.com
SMTP_PASSWORD=your-fastmail-app-password
SMTP_STARTTLS=true
```

Then change this line in `feeds.yaml`:

```yaml
to:
  - you@fastmail.com
```

And replace the local Mailpit SMTP fields with the Fastmail values above.

### AWS SES

1. Create SMTP credentials in AWS SES.
2. Verify the sender identity you will use in `from:`.
3. Edit `.env` with these values:

```dotenv
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-ses-smtp-username
SMTP_PASSWORD=your-ses-smtp-password
SMTP_STARTTLS=true
```

Then change this line in `feeds.yaml`:

```yaml
to:
  - you@example.com
```

And replace the local Mailpit SMTP fields with the SES values above.

## What the feed does

| Setting | Value |
|---|---|
| Schedule | Every Monday at 09:00 UTC (`0 9 * * 1`) |
| Feed name | `weekly-digest` |
| Sources | Simon Willison Atom + HN RSS query for `AI` |
| Pipeline | `dedup → rank → summarize → digest` |
| Ranking filter | practical AI engineering relevance, `min_relevance: 0.5` |
| Summary style | one sentence, ≤25 words, fact-first |
| LLM | `ollama:qwen2.5:7b` at `http://ollama:11434` |
| Subject | `[glean] {feed_name} — {date}` |
| Sinks | `email` + `dashboard` (`keep_last_n: 25`) |
| Bootstrap | `skip-and-mark` |

## Customizing

- **Change the schedule** by editing `schedule: "0 9 * * 1"` (Monday 09:00 UTC)
- **Add or swap RSS sources** by duplicating or replacing the `- type: rss` blocks under `sources:`
- **Swap the LLM** by editing `defaults.llm.model` and pulling the replacement into Ollama

After editing `feeds.yaml`, restart glean:

```bash
docker compose -f docker-compose.yml restart glean
```

## Browsing digests in the dashboard

Open <http://127.0.0.1:9096/> to browse recent digests stored by the dashboard sink.

If `GLEAN_API_KEY` is blank, glean auto-generates one on first boot and prints it to the container logs:

```bash
docker compose -f docker-compose.yml logs glean | grep GLEAN_INITIAL_API_KEY | head -1
```

Paste that key into the web UI when prompted.

## Teardown

```bash
./teardown.sh
```

```powershell
./teardown.ps1
```

This stops the containers, removes volumes, deletes `data/`, and removes the local `.env` so you can start fresh.

## Going further

- [Dashboard sink how-to](../../docs/how-to/sinks/dashboard.md)
- [Pipeline concepts](../../docs/concepts/pipeline.md)
- [Concepts index](../../docs/concepts/index.md)
